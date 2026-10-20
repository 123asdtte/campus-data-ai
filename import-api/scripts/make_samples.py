"""生成虚构导入样例文件（不含任何真实学生信息）。

运行方式（容器内）：
    docker compose run --rm import-api python scripts/make_samples.py

输出到 /app/samples：
    students_clean.xlsx         全部合法，用于验证正常导入
    students_demo.xlsx          含 5 类结构性异常，用于验证校验
    student_changes_demo.xlsx   含未知学号、非法日期、非法枚举
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import psycopg

OUTPUT_DIR = os.environ.get("SAMPLE_DIR", "/app/samples")

STUDENT_HEADERS = ["学号", "姓名", "学院", "专业", "班级", "入学年份", "在校状态"]
CHANGE_HEADERS = ["学号", "异动类型", "生效日期", "异动原因", "记录状态"]


def fetch_student_numbers(limit: int = 8) -> list[str]:
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT student_no FROM campus.students WHERE is_active ORDER BY student_no LIMIT %s",
            (limit,),
        )
        return [row[0] for row in cur.fetchall()]


def next_sample_serial() -> int:
    """取一个未被占用的 SMPL 学号段，保证样例可反复导入而不误报重复。"""
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT max(student_no) FROM campus.students WHERE student_no LIKE 'SMPL%'")
        row = cur.fetchone()
    if not row or not row[0]:
        return 20260001
    digits = "".join(ch for ch in row[0] if ch.isdigit())
    return int(digits) + 1 if digits else 20260001


def build_students_clean(start: int) -> pd.DataFrame:
    rows = []
    colleges = [
        ("计算机学院", "软件技术"),
        ("电子信息学院", "物联网应用技术"),
        ("经济管理学院", "大数据与会计"),
    ]
    for i in range(10):
        college, major = colleges[i % len(colleges)]
        rows.append(
            [
                f"SMPL{start + i:08d}",
                f"测试学生{start % 100:02d}{i:02d}",
                college,
                major,
                f"{major}2026级{i % 3 + 1}班",
                2026,
                "在校",
            ]
        )
    return pd.DataFrame(rows, columns=STUDENT_HEADERS)


def build_students_demo(start: int) -> pd.DataFrame:
    df = build_students_clean(start)
    first_no = df.at[0, "学号"]
    base = start + 100
    bad_rows = pd.DataFrame(
        [
            # 1) 姓名缺失 → MISSING_REQUIRED
            [f"SMPL{base:08d}", "", "计算机学院", "软件技术", "软件技术2026级1班", 2026, "在校"],
            # 2) 学号与第 1 行重复 → DUPLICATE_STUDENT_NO
            [first_no, "重复学号", "计算机学院", "软件技术", "软件技术2026级1班", 2026, "在校"],
            # 3) 入学年份非数字 → INVALID_ENUM
            [f"SMPL{base + 2:08d}", "年份异常", "电子信息学院", "物联网应用技术", "物联网2026级2班", "两千二四", "在校"],
            # 4) 在校状态不在受控范围 → INVALID_ENUM
            [f"SMPL{base + 3:08d}", "状态异常", "经济管理学院", "大数据与会计", "会计2026级3班", 2026, "在读"],
            # 5) 姓名超长（105 字符）→ VALUE_TOO_LONG
            [f"SMPL{base + 4:08d}", "超" * 105, "艺术学院", "视觉传达设计", "设计2026级1班", 2026, "在校"],
        ],
        columns=STUDENT_HEADERS,
    )
    return pd.concat([df, bad_rows], ignore_index=True)


def build_changes_demo(student_numbers: list[str]) -> pd.DataFrame:
    base = student_numbers[:5] or ["SMPL20260001"]
    rows = [
        [base[0], "休学", "2026-03-01", "因身体原因申请休学", "已确认"],
        [base[1 % len(base)], "复学", "2026-09-01", "休学期满复学", "已确认"],
        [base[2 % len(base)], "转专业", "2026-07-15", "依据个人志愿调整专业", "待复核"],
        [base[3 % len(base)], "保留学籍", "2026-02-20", "参军入伍", "草稿"],
        [base[4 % len(base)], "其他", "2026-05-06", "其他学籍异动", "已退回"],
        # 6) 数据库中不存在的学号 → UNKNOWN_STUDENT
        ["DEMO9999999999", "休学", "2026-04-01", "未知学生", "草稿"],
        # 7) 非法日期 → INVALID_DATE
        [base[0], "休学", "2026-13-45", "日期格式错误", "草稿"],
        # 8) 非法异动类型 → INVALID_ENUM
        [base[0], "出国", "2026-06-01", "类型不在受控范围", "草稿"],
        # 9) 学号缺失 → MISSING_REQUIRED
        ["", "复学", "2026-09-10", "缺少学号", "草稿"],
    ]
    return pd.DataFrame(rows, columns=CHANGE_HEADERS)


def main() -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    students = fetch_student_numbers()
    start = next_sample_serial()

    outputs = {
        "students_clean.xlsx": build_students_clean(start),
        "students_demo.xlsx": build_students_demo(start),
        "student_changes_demo.xlsx": build_changes_demo(students),
    }

    for name, frame in outputs.items():
        path = os.path.join(OUTPUT_DIR, name)
        frame.to_excel(path, index=False, engine="openpyxl")
        print(f"written {path}  rows={len(frame)}")

    print("参考学号：", ", ".join(students[:5]) or "(数据库为空)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
