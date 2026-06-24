"""
db/connection.py — PostgreSQL connection pool for the Data Ingestion System.
No Django, no ORM. Pure psycopg2.
"""
import os
from typing import Optional

import psycopg2
from psycopg2 import pool

_pool: Optional[pool.ThreadedConnectionPool] = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        _pool = pool.ThreadedConnectionPool(minconn=1, maxconn=15, dsn=dsn)
    return _pool


def get_conn():
    """Get a connection from the pool. Always return it with put_conn()."""
    return _get_pool().getconn()


def put_conn(conn):
    """Return a connection to the pool."""
    _get_pool().putconn(conn)


class DBConn:
    """Context manager for a pooled connection with auto-commit on success."""

    def __enter__(self):
        self.conn = get_conn()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        put_conn(self.conn)
        return False
