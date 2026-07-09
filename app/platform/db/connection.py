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
from typing import Any, Generator

from app.config import settings

_conn: Any = None


def postgres_enabled() -> bool:
    return bool(settings.DATABASE_URL and str(settings.DATABASE_URL).strip())


def get_connection():
    global _conn
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured")
    if _conn is None or _conn.closed:
        import psycopg2

        _conn = psycopg2.connect(settings.DATABASE_URL)
        _conn.autocommit = False
    return _conn


@contextlib.contextmanager
def db_cursor() -> Generator[Any, None, None]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def reset_connection() -> None:
    global _conn
    if _conn is not None and not _conn.closed:
        _conn.close()
    _conn = None
