#!/usr/bin/env python
"""上线前预检（只读）。

检查目标：在不修改任何配置或数据的前提下，快速确认“正式上线阻断项”是否已闭环。
用法：python scripts/preflight.py
退出码：0 = 无 FAIL（允许 SKIP/WARN）；1 = 存在 FAIL。

说明：
- 本脚本只读取仓库文件、compose 配置、容器状态与数据库权限；
- 不会执行迁移、恢复、写入或重启；
- 不打印任何密钥值，只检查长度/占位符/默认值。
"""
from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS: list[tuple[str, str, str]] = []  # (级别, 检查项, 说明)


def add(level: str, name: str, detail: str = "") -> None:
    """记录一条检查结果。级别：PASS / FAIL / WARN / SKIP。"""
    RESULTS.append((level, name, detail))


def read_env() -> dict[str, str]:
    """读取 .env 的 KEY=VALUE（不输出值）。"""
    env_path = ROOT / ".env"
    data: dict[str, str] = {}
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    """执行只读命令，统一 UTF-8 解码。"""
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def compose_json() -> dict | None:
    """获取 compose 解析后的配置；失败返回 None。"""
    proc = run(["docker", "compose", "config", "--format", "json"])
    if proc.returncode != 0:
        add("FAIL", "compose 配置可解析", (proc.stderr or "").strip()[:200])
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        add("FAIL", "compose 配置可解析", f"JSON 解析失败：{exc}")
        return None


def check_ports(config: dict) -> None:
    """所有发布端口必须只绑定回环地址；import-api 不得有宿主端口。"""
    bad: list[str] = []
    for name, svc in (config.get("services") or {}).items():
        for port in svc.get("ports") or []:
            host_ip = (port or {}).get("host_ip") or ""
            published = (port or {}).get("published")
            if host_ip not in ("127.0.0.1", "::1"):
                bad.append(f"{name}:{published}(host_ip={host_ip or '*'})")
    if bad:
        add("FAIL", "端口仅绑定回环", "、".join(bad))
    else:
        add("PASS", "端口仅绑定回环", "全部为 127.0.0.1/::1")

    import_api = (config.get("services") or {}).get("import-api") or {}
    if import_api.get("ports"):
        add("FAIL", "import-api 无宿主端口", "存在 ports 配置（应仅容器内网）")
    else:
        add("PASS", "import-api 无宿主端口", "未发布到宿主")


def check_gateway(config: dict, env_map: dict[str, str]) -> None:
    """网关配置检查：healthcheck、JWT 密钥外部化、Actuator 收敛。"""
    gateway = (config.get("services") or {}).get("gateway") or {}
    if gateway.get("healthcheck"):
        add("PASS", "网关 healthcheck", "已定义")
    else:
        add("FAIL", "网关 healthcheck", "compose 未定义")

    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    if "JWT_SECRET_KEY" in compose_text:
        add("PASS", "JWT 密钥由环境提供", "compose 已引用 JWT_SECRET_KEY")
    else:
        add("FAIL", "JWT 密钥由环境提供", "compose 未引用 JWT_SECRET_KEY")

    key = env_map.get("JWT_SECRET_KEY", "")
    if not key:
        add("FAIL", "JWT 密钥长度", ".env 缺少 JWT_SECRET_KEY")
    elif key.startswith("__CHANGE_ME"):
        add("FAIL", "JWT 密钥长度", "仍为占位符")
    elif len(key) < 32:
        add("FAIL", "JWT 密钥长度", f"仅 {len(key)} 字符（要求 ≥32）")
    else:
        add("PASS", "JWT 密钥长度", f"{len(key)} 字符")

    app_yml = ROOT / "gateway/ruoyi-admin/src/main/resources/application.yml"
    text = app_yml.read_text(encoding="utf-8")
    if re.search(r"jwt-secret-key:\s*abcdefghijklmnopqrstuvwxyz", text):
        add("FAIL", "仓库内无固定 JWT 密钥", "application.yml 仍写死默认值")
    elif re.search(r"jwt-secret-key:\s*\$\{JWT_SECRET_KEY", text):
        add("PASS", "仓库内无固定 JWT 密钥", "已使用环境变量占位")
    else:
        add("WARN", "仓库内无固定 JWT 密钥", "未找到预期配置，请人工确认")

    if re.search(r"include:\s*['\"]?\*['\"]?", text):
        add("FAIL", "Actuator 暴露面", "仍为 include: '*'")
    elif re.search(r"include:\s*health\s*,\s*info", text):
        add("PASS", "Actuator 暴露面", "仅 health,info")
    else:
        add("WARN", "Actuator 暴露面", "未找到最小暴露配置")


def check_restore() -> None:
    """恢复脚本必须重放 006 并校验权限。"""
    path = ROOT / "scripts/restore.sh"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = []
    if "006_import_scope.sql" not in text:
        missing.append("未重放 006")
    if "has_table_privilege" not in text:
        missing.append("缺少权限断言")
    if missing:
        add("FAIL", "恢复流程权限收口", "；".join(missing))
    else:
        add("PASS", "恢复流程权限收口", "重放 006 并断言 DELETE=f")


def check_backup() -> None:
    """最近备份必须存在且 gzip 完整。"""
    files = sorted((ROOT / "backups").glob("campus_*.sql.gz"), key=lambda p: p.stat().st_mtime)
    if not files:
        add("FAIL", "备份文件可读", "backups/ 下没有 campus_*.sql.gz")
        return
    latest = files[-1]
    try:
        with gzip.open(latest, "rb") as fh:
            while fh.read(1024 * 1024):
                pass
        age_h = (time.time() - latest.stat().st_mtime) / 3600
        add("PASS", "备份文件可读", f"{latest.name}，{age_h:.1f} 小时前")
    except OSError as exc:
        add("FAIL", "备份文件可读", f"{latest.name}: {exc}")


def check_db_privilege(env_map: dict[str, str]) -> None:
    """业务库权限：campus_app 不得直接 DELETE import_issues。"""
    proc = run(["docker", "inspect", "-f", "{{.State.Running}}", "campus-db"])
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        add("SKIP", "数据库权限", "campus-db 未运行")
        return
    user = env_map.get("POSTGRES_USER", "campus_dba")
    db = env_map.get("POSTGRES_DB", "campus")
    proc = run(
        [
            "docker",
            "exec",
            "campus-db",
            "psql",
            "-U",
            user,
            "-d",
            db,
            "-tAc",
            "SELECT has_table_privilege('campus_app','campus.import_issues','DELETE');",
        ]
    )
    value = proc.stdout.strip()
    if proc.returncode != 0:
        add("SKIP", "数据库权限", (proc.stderr or "").strip()[:120])
    elif value == "f":
        add("PASS", "数据库权限", "campus_app 无 DELETE import_issues")
    else:
        add("FAIL", "数据库权限", f"DELETE 权限为 {value or '空'}（应为 f）")


def check_health() -> None:
    """网关公开探针必须可访问。"""
    url = "http://127.0.0.1:8082/gw/healthz"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read(16).decode(errors="ignore")
        if resp.status == 200 and body.startswith("ok"):
            add("PASS", "网关健康探针", "/gw/healthz=200")
        else:
            add("FAIL", "网关健康探针", f"HTTP {resp.status}，body={body!r}")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        add("FAIL", "网关健康探针", f"{url} 不可达：{exc}")


def check_tls() -> None:
    """生产入口必须具备 443 与证书配置。"""
    conf = ROOT / "web/nginx.conf"
    text = conf.read_text(encoding="utf-8") if conf.exists() else ""
    if "listen" in text and "443" in text and "ssl_certificate" in text:
        add("PASS", "TLS 入口", "nginx 已配置 443 与证书")
    else:
        add("FAIL", "TLS 入口", "nginx 仅 80，未配置证书")


def check_monitoring(config: dict) -> None:
    """至少存在指标采集或告警组件。"""
    services = (config.get("services") or {}).keys()
    expected = {"prometheus", "grafana", "loki", "alertmanager"}
    found = sorted(set(services) & expected)
    if found:
        add("PASS", "监控组件", "、".join(found))
    else:
        add("FAIL", "监控组件", "compose 未包含 Prometheus/Grafana/Loki/Alertmanager")


def check_internal_auth(env_map: dict[str, str]) -> None:
    """正式切换前必须保持 false；此检查只提示当前状态。"""
    value = env_map.get("INTERNAL_AUTH_ENABLED", "false").lower()
    if value in ("false", "0", "no", ""):
        add("PASS", "内部认证开关", "当前 false（正式切换前预期）")
    else:
        add("WARN", "内部认证开关", "当前已开启，请确认已获正式切换批准")


def check_artifact() -> None:
    """生产镜像 jar 不得包含 application-dev.yml / application-prod.yml。

    这两份文件被 .gitignore 排除，但默认构建仍会把本地文件打进 jar；
    生产必须使用 -Pprod 构建（见 ruoyi-admin/pom.xml 的 prod profile）。
    """
    jar = ROOT / "gateway/ruoyi-admin/target/ruoyi-admin.jar"
    if not jar.exists():
        add("SKIP", "镜像配置卫生", "未找到构建产物 jar")
        return
    try:
        with zipfile.ZipFile(jar) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        add("FAIL", "镜像配置卫生", f"jar 无法读取：{exc}")
        return
    leaked = sorted({n for n in names if n.endswith(("application-dev.yml", "application-prod.yml"))})
    if leaked:
        add("FAIL", "镜像配置卫生", f"jar 含本地配置（{len(leaked)} 项），请用 -Pprod 构建")
    else:
        add("PASS", "镜像配置卫生", "jar 未包含本地配置")


def main() -> int:
    env_map = read_env()
    if not env_map:
        add("FAIL", "环境文件", "缺少 .env（无法做配置检查）")
    else:
        add("PASS", "环境文件", ".env 存在（未输出任何值）")

    config = compose_json()
    if config:
        check_ports(config)
        check_gateway(config, env_map)
        check_monitoring(config)

    check_restore()
    check_backup()
    check_db_privilege(env_map)
    check_health()
    check_tls()
    check_internal_auth(env_map)
    check_artifact()

    width = max(len(name) for _, name, _ in RESULTS)
    for level, name, detail in RESULTS:
        print(f"[{level:4}] {name.ljust(width)}  {detail}")
    fails = sum(1 for level, _, _ in RESULTS if level == "FAIL")
    print(f"\n合计：{len(RESULTS)} 项，FAIL={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
