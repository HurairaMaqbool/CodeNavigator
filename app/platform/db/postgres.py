"""
app/platform/db/postgres.py
-----------------------------
Schema bootstrap and health check.
"""
from __future__ import annotations

from pathlib import Path

from app.platform.db.connection import db_cursor, postgres_enabled, reset_connection


def check_connection() -> bool:
    if not postgres_enabled():
        return False
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        reset_connection()
        return False


def apply_schema() -> None:
    if not postgres_enabled():
        return
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with db_cursor() as cur:
        cur.execute(schema)
