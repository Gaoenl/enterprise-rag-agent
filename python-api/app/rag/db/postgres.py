"""PostgreSQL connection pool management."""

from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from psycopg import Connection
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from app.config import get_settings


_pool: ConnectionPool | None = None
_pool_lock = Lock()


def init_connection_pool() -> ConnectionPool:
    """创建并预热当前 Python 进程的数据库连接池。"""
    global _pool

    if _pool is not None:
        return _pool

    # 防止多个请求同时初始化多个连接池。
    with _pool_lock:
        if _pool is not None:
            return _pool

        settings = get_settings()

        # 使用 make_conninfo 安全处理密码中的特殊字符。
        conninfo = make_conninfo(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            connect_timeout=(
                settings.postgres_connect_timeout_seconds
            ),
        )

        pool = ConnectionPool(
            conninfo=conninfo,
            min_size=settings.postgres_pool_min_size,
            max_size=settings.postgres_pool_max_size,
            timeout=settings.postgres_pool_timeout_seconds,
            open=False,
        )

        # 启动并等待 min_size 个连接准备完成。
        pool.open(
            wait=True,
            timeout=settings.postgres_connect_timeout_seconds,
        )

        _pool = pool
        return pool


def get_connection_pool() -> ConnectionPool:
    """获取连接池；未初始化时执行兜底初始化。"""
    if _pool is None:
        return init_connection_pool()

    return _pool


@contextmanager
def get_connection() -> Iterator[Connection]:
    """从连接池借用连接，并在使用完成后自动归还。"""
    pool = get_connection_pool()

    # 正常结束时提交事务，发生异常时回滚事务。
    with pool.connection() as connection:
        yield connection


def close_connection_pool() -> None:
    """关闭当前进程的数据库连接池。"""
    global _pool

    with _pool_lock:
        pool = _pool
        _pool = None

    if pool is not None:
        pool.close()