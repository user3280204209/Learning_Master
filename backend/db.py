"""数据库访问层：连接池 + 主从读写分离。

设计要点（对应第 17、19 课）：
1. 写走 3306 主库，读走 3307 从库——显式选择，不解析 SQL。
2. 用线程安全池复用连接，避免每个请求三次握手。
3. 从库不可用时自动降级到主库；降级会打 WARNING，便于发现环境问题。
4. 「写后立刻读」走 `write_conn()`，避免主从延迟读到旧数据。
"""
from __future__ import annotations

import logging
import queue
import threading
from contextlib import contextmanager
from typing import Iterator

import pymysql

from config import (
    DB_CHARSET,
    DB_CONNECT_TIMEOUT,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_POOL_SIZE,
    DB_USER,
    READ_DB_PORT,
    WRITE_DB_PORT,
)

logger = logging.getLogger(__name__)

BASE_CONFIG = {
    "host": DB_HOST,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": DB_NAME,
    "charset": DB_CHARSET,
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
    "connect_timeout": DB_CONNECT_TIMEOUT,
    "read_timeout": 15,
    "write_timeout": 15,
}

WRITE_CONFIG = {**BASE_CONFIG, "port": WRITE_DB_PORT}
READ_CONFIG = {**BASE_CONFIG, "port": READ_DB_PORT}


class ConnectionPool:
    """极简连接池：LIFO 复用 + 池满阻塞 + 失效连接自动重建。

    生产环境直接用 SQLAlchemy / DBUtils，这里手写一遍是为了看清原理：
    池只是把「创建连接」这个昂贵动作从每次请求挪到了第一次请求。
    """

    def __init__(self, config: dict, name: str, max_size: int = DB_POOL_SIZE):
        self.config = config
        self.name = name
        self.max_size = max_size
        self._pool: queue.LifoQueue = queue.LifoQueue(maxsize=max_size)
        self._lock = threading.Lock()
        self._created = 0

    def _new_connection(self) -> pymysql.Connection:
        return pymysql.connect(**self.config)

    def acquire(self) -> pymysql.Connection:
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self.max_size:
                    self._created += 1
                    try:
                        return self._new_connection()
                    except Exception:
                        self._created -= 1
                        raise
            # 池满：最多等 5 秒，等不到就报错，避免请求无限堆积
            try:
                conn = self._pool.get(timeout=5)
            except queue.Empty as exc:
                raise RuntimeError(f"{self.name} 连接池已耗尽") from exc

        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            self._discard(conn)
            return self.acquire()

    def release(self, conn: pymysql.Connection, broken: bool = False) -> None:
        if broken:
            self._discard(conn)
            return
        try:
            conn.rollback()  # 清理未提交事务，避免状态泄漏给下一个请求
            self._pool.put_nowait(conn)
        except Exception:
            self._discard(conn)

    def _discard(self, conn: pymysql.Connection) -> None:
        try:
            conn.close()
        except Exception:
            pass
        with self._lock:
            self._created = max(0, self._created - 1)

    @contextmanager
    def connection(self) -> Iterator[pymysql.Connection]:
        conn = self.acquire()
        broken = False
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                broken = True
            raise
        finally:
            # 连接级异常（断线）才销毁；SQL 语法错误不销毁连接
            if not conn.open:
                broken = True
            self.release(conn, broken=broken)

    def close_all(self) -> None:
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                break
            self._discard(conn)


write_pool = ConnectionPool(WRITE_CONFIG, "write", max_size=DB_POOL_SIZE)
read_pool = ConnectionPool(READ_CONFIG, "read", max_size=DB_POOL_SIZE)


def write_conn() -> Iterator[pymysql.Connection]:
    """写连接（也是需要「读到自己刚写的数据」时用的连接）。"""
    return write_pool.connection()


@contextmanager
def read_conn() -> Iterator[pymysql.Connection]:
    """读连接。从库不可用时降级主库，并记录原因。"""
    try:
        conn = read_pool.acquire()
    except Exception as exc:
        logger.warning("从库 %s:%s 不可用，读请求降级主库：%s", DB_HOST, READ_DB_PORT, exc)
        with write_pool.connection() as fallback:
            yield fallback
        return

    broken = False
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            broken = True
        raise
    finally:
        if not conn.open:
            broken = True
        read_pool.release(conn, broken=broken)


def fetch_all(sql: str, params: tuple = (), *, use_master: bool = False) -> list[dict]:
    conn_ctx = write_conn() if use_master else read_conn()
    with conn_ctx as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def fetch_one(sql: str, params: tuple = (), *, use_master: bool = False) -> dict | None:
    conn_ctx = write_conn() if use_master else read_conn()
    with conn_ctx as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    """执行写语句，返回 lastrowid（INSERT）或受影响行数。"""
    with write_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid or cur.rowcount


def execute_many(sql: str, rows: list[tuple]) -> int:
    if not rows:
        return 0
    with write_conn() as conn:
        with conn.cursor() as cur:
            return cur.executemany(sql, rows)


def health() -> dict:
    """给 /api/health 用：分别探测主库与从库。"""
    result = {}
    for name, pool in (("master", write_pool), ("replica", read_pool)):
        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    cur.fetchone()
            result[name] = {"ok": True, "port": pool.config["port"]}
        except Exception as exc:
            result[name] = {"ok": False, "port": pool.config["port"], "error": str(exc)[:160]}
    return result


def close_pools() -> None:
    write_pool.close_all()
    read_pool.close_all()
