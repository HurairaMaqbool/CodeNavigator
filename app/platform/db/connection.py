# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/db/connection.py
-----------------------------
PostgreSQL connection helper (optional; JSON fallback when unset).
"""
from __future__ import annotations

import contextlib
import threading
from typing import Any, Generator

from app.config import settings

_pool: Any = None
_pool_lock = threading.Lock()


def postgres_enabled() -> bool:
    return bool(settings.DATABASE_URL and str(settings.DATABASE_URL).strip())


def _get_pool():
    global _pool
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured")
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg2.pool import ThreadedConnectionPool
                # Min 1, max 20 connections in pool
                _pool = ThreadedConnectionPool(1, 20, settings.DATABASE_URL)
    return _pool


@contextlib.contextmanager
def db_cursor() -> Generator[Any, None, None]:
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured")
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


def reset_connection() -> None:
    global _pool
    if _pool is not None:
        with _pool_lock:
            if _pool is not None:
                try:
                    _pool.closeall()
                except Exception:
                    pass
                _pool = None

