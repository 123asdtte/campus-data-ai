"""PR-E 专项：并发、事务、nonce 清理、大文件、审计批量与配置失败。

本文件只在开启态进程运行（`INTERNAL_AUTH_ENABLED=true`），
因为多数用例需要可信身份签名与 nonce 表。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests import auth_helper as H

AUTH_ENABLED = os.environ.get("INTERNAL_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(not AUTH_ENABLED, reason="仅在开启态进程运行")

API_DIR = Path(__file__).resolve().parent.parent

CSV_HEADER = "学号,姓名,学院,专业,班级,入学年份,在校状态\n"


def _csv(rows: list[tuple[str, str, str]]) -> bytes:
    """生成学生导入 CSV；rows=(学号, 姓名, 学院)。"""
    body = "".join(f"{no},{name},{college},软件技术,软件2601,2026,在校\n" for no, name, college in rows)
    return (CSV_HEADER + body).encode("utf-8")


def _new_client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def seeded_student(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO campus.students (student_no, student_name, college_name, class_name, student_status)
            VALUES ('SA001', '甲同学', '计算机学院', '软件2601', 'enrolled')
            ON CONFLICT (student_no) DO NOTHING
            """
        )
    return None


# ---------------------------------------------------------------- 并发更新
def test_并发学生更新_两次审计都保留(db_client, admin_conn, seeded_student):
    barrier = threading.Barrier(2)
    results: list[tuple[int, str, str]] = []

    def worker(name: str, user: str) -> None:
        client = _new_client()
        barrier.wait()
        who = {**H.WHO_COLLEGE, "user": user}
        response = H.request(client, "PUT", "/students/SA001",
                             json_body={"student_name": name}, who=who)
        results.append((response.status_code, name, response.text))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, "并发甲", "ry:college_a"),
                   pool.submit(worker, "并发乙", "ry:college_b_actor")]
        for future in futures:
            future.result()

    assert [r[0] for r in results] == [200, 200], results
    with admin_conn.cursor() as cur:
        cur.execute("SELECT student_name FROM campus.students WHERE student_no = 'SA001'")
        final_name = cur.fetchone()[0]
        cur.execute(
            """
            SELECT count(*), count(DISTINCT actor_user_id)
              FROM campus.operation_logs
             WHERE object_type = 'students'
               AND action = 'update'
               AND object_id = (SELECT id::text FROM campus.students WHERE student_no = 'SA001')
            """
        )
        audit_count, actor_count = cur.fetchone()
    assert final_name in {"并发甲", "并发乙"}
    assert audit_count == 2, "两个并发更新都必须各有审计记录，不能丢失"
    assert actor_count == 2, "并发更新的审计操作人必须分别记录"


# ---------------------------------------------------------------- 并发提交
def test_并发导入提交_仅一次成功且数据不重复(db_client, admin_conn):
    rows = [("PE2026102201", "并发甲", "计算机学院"),
            ("PE2026102202", "并发乙", "计算机学院"),
            ("PE2026102203", "并发丙", "计算机学院")]
    preview = H.request(db_client, "POST", "/imports/preview",
                        file_bytes=_csv(rows), form={"target_type": "students"})
    assert preview.status_code == 200, preview.text
    batch_id = preview.json()["batch_id"]
    validated = H.request(db_client, "POST", f"/imports/{batch_id}/validate")
    assert validated.status_code == 200, validated.text
    assert validated.json()["valid_rows"] == 3

    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def commit() -> None:
        client = _new_client()
        barrier.wait()
        response = H.request(client, "POST", f"/imports/{batch_id}/commit")
        statuses.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(commit), pool.submit(commit)]
        for future in futures:
            future.result()

    assert sorted(statuses) == [200, 409], statuses
    with admin_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM campus.students WHERE student_no LIKE 'PE20261022%'")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT batch_status FROM campus.import_batches WHERE id = %s", (batch_id,))
        assert cur.fetchone()[0] == "imported"


# ---------------------------------------------------------------- nonce
def test_nonce_清理只删除过期行且可重复执行(db_client, admin_conn):
    expired = "expired-" + uuid.uuid4().hex[:20]
    fresh = "fresh-" + uuid.uuid4().hex[:20]
    with admin_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO campus.internal_nonce (nonce, expires_at) VALUES (%s, now() - interval '1 hour')",
            (expired,),
        )
        cur.execute(
            "INSERT INTO campus.internal_nonce (nonce, expires_at) VALUES (%s, now() + interval '1 hour')",
            (fresh,),
        )

    from app.internal_auth import cleanup_nonce

    assert cleanup_nonce() >= 1
    assert cleanup_nonce() == 0
    with admin_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM campus.internal_nonce WHERE nonce = %s", (expired,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM campus.internal_nonce WHERE nonce = %s", (fresh,))
        assert cur.fetchone()[0] == 1


def test_nonce_增长与表空间记录(db_client, admin_conn):
    """记录 1000 条 nonce 的物理占用；不做脆弱阈值断言，输出供评审引用。"""
    count = 1000
    with admin_conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO campus.internal_nonce (nonce) VALUES (%s)",
            [(uuid.uuid4().hex,) for _ in range(count)],
        )
        cur.execute("SELECT count(*), pg_total_relation_size('campus.internal_nonce') FROM campus.internal_nonce")
        rows, size = cur.fetchone()
    print(f"[nonce] rows={rows} total_relation_size={size} bytes ({size / 1024:.1f} KiB)")
    assert rows == count
    assert size < 4 * 1024 * 1024, "1000 条 nonce 不应占用超过 4MB"


# ---------------------------------------------------------------- 大文件
def test_大文件预览_接近10MB可处理(db_client):
    # 每行姓名填充到约 900 字节，9000 行 ≈ 8.1MB，低于 10MB 上限
    filler = "测" * 300
    rows = [(f"LF{i:06d}", filler, "计算机学院") for i in range(9000)]
    data = _csv(rows)
    assert 7 * 1024 * 1024 < len(data) < 10 * 1024 * 1024, len(data)

    started = time.monotonic()
    response = H.request(db_client, "POST", "/imports/preview",
                         file_bytes=data, form={"target_type": "students"})
    elapsed = time.monotonic() - started
    print(f"[large-file] bytes={len(data)} elapsed={elapsed:.2f}s")
    assert response.status_code == 200, response.text
    assert response.json()["total_rows"] == 9000
    assert elapsed < 120, f"9MB 预览耗时异常：{elapsed:.1f}s"


def test_超过10MB直接拒绝(db_client):
    data = (CSV_HEADER + ("X" * 1024 + "\n") * 11000).encode()
    assert len(data) > 10 * 1024 * 1024
    response = H.request(db_client, "POST", "/imports/preview",
                         file_bytes=data, form={"target_type": "students"})
    assert response.status_code == 413, response.text
    assert "上限" in response.json()["detail"]


# ---------------------------------------------------------------- 批量审计
def test_批量提交1000行_审计完整(db_client, admin_conn):
    rows = [(f"PB{i:06d}", f"批量{i}", "计算机学院") for i in range(1000)]
    preview = H.request(db_client, "POST", "/imports/preview",
                        file_bytes=_csv(rows), form={"target_type": "students"})
    assert preview.status_code == 200, preview.text
    batch_id = preview.json()["batch_id"]
    assert H.request(db_client, "POST", f"/imports/{batch_id}/validate").status_code == 200

    started = time.monotonic()
    commit = H.request(db_client, "POST", f"/imports/{batch_id}/commit")
    elapsed = time.monotonic() - started
    print(f"[batch-audit] rows=1000 commit_elapsed={elapsed:.2f}s")
    assert commit.status_code == 200, commit.text
    assert commit.json()["inserted_rows"] == 1000

    with admin_conn.cursor() as cur:
        # 提交成功后：暂存文件必须删除，staged_path 置 NULL
        cur.execute("SELECT staged_path FROM campus.import_batches WHERE id = %s", (batch_id,))
        staged_path = cur.fetchone()[0]
        assert staged_path is None, f"staged_path 未清空：{staged_path}"
        cur.execute(
            """
            SELECT count(*) FROM campus.operation_logs
             WHERE object_type = 'students'
               AND actor_user_id = 'ry:college_a'
               AND object_id IN (SELECT id::text FROM campus.students WHERE student_no LIKE 'PB%')
            """
        )
        assert cur.fetchone()[0] == 1000
        cur.execute("SELECT count(*) FROM campus.operation_logs WHERE object_type = 'import_batches' AND object_id = %s",
                    (str(batch_id),))
        assert cur.fetchone()[0] >= 2, "批次应至少有上传/校验/提交的审计记录"
        # 提交后的 staged_path 清理是独立事务，也必须带可信 actor
        cur.execute(
            "SELECT count(*) FROM campus.operation_logs "
            "WHERE object_type = 'import_batches' AND object_id = %s "
            "AND (actor_user_id IS NULL OR btrim(actor_user_id) = '')",
            (str(batch_id),),
        )
        assert cur.fetchone()[0] == 0, "导入批次审计不得出现匿名操作人"


def test_nonce周期清理任务会重复执行(monkeypatch):
    """验证后台清理循环不是一次性：间隔到期后会再次调用清理函数。"""
    import asyncio
    from contextlib import suppress

    from app import main as app_main

    calls: list[int] = []
    monkeypatch.setattr(app_main, "NONCE_CLEANUP_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(app_main.internal_auth, "cleanup_nonce", lambda: calls.append(1) or 0)

    async def run() -> None:
        task = asyncio.create_task(app_main._nonce_cleanup_loop())
        await asyncio.sleep(0.06)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert len(calls) >= 2, f"周期清理应至少执行两次，实际 {len(calls)}"


# ---------------------------------------------------------------- 配置失败
def _import_config(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_开启认证但密钥过短_启动失败():
    result = _import_config({"INTERNAL_AUTH_ENABLED": "true", "INTERNAL_HMAC_SECRET": "short"})
    assert result.returncode != 0
    assert "至少 32" in (result.stderr + result.stdout)


def test_开启认证但密钥缺失_启动失败():
    result = _import_config({"INTERNAL_AUTH_ENABLED": "true", "INTERNAL_HMAC_SECRET": ""})
    assert result.returncode != 0
    assert "至少 32" in (result.stderr + result.stdout)


def test_时间窗配置越界_启动失败():
    result = _import_config({"INTERNAL_AUTH_MAX_SKEW_SECONDS": "0"})
    assert result.returncode != 0
    assert "1..600" in (result.stderr + result.stdout)
