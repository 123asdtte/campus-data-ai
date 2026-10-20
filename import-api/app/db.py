"""数据库连接池。仅使用 campus_app 最小权限账号，不持有 DDL 权限。"""
from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
    open=False,
    timeout=15,
)


def open_pool() -> None:
    pool.open(wait=True, timeout=30)


def close_pool() -> None:
    pool.close()
