"""数据库连接：读连接与审计连接物理分离。

- 读连接使用 ai_ro：只有 SELECT，无法写业务表；
- 审计连接使用 ai_audit_writer：只能 INSERT ai.audit，不能读业务表。
即使代码出现 bug，也无法用读连接篡改数据；审计连接也读不到学生信息。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import SETTINGS


@contextmanager
def read_cursor() -> Iterator[psycopg.Cursor]:
    with psycopg.connect(SETTINGS.ro_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            yield cur


@contextmanager
def audit_connection() -> Iterator[psycopg.Cursor]:
    with psycopg.connect(SETTINGS.audit_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            yield cur
