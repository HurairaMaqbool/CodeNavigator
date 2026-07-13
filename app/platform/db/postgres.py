# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

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
    try:
        migrate_json_to_pg()
    except Exception as exc:
        from app.observability.logging_config import logger
        logger.warning("migration_json_to_pg_failed", error=str(exc))


def migrate_json_to_pg() -> None:
    if not postgres_enabled():
        return
    import json
    from pathlib import Path
    from app.paths import data_path
    from app.observability.logging_config import logger

    # 1. API Keys migration
    keys_path = data_path("api_keys.json")
    if keys_path.exists():
        try:
            data = json.loads(keys_path.read_text(encoding="utf-8"))
            keys_dict = data.get("keys") or {}
            for key_id, meta in keys_dict.items():
                org_id = meta.get("org_id", "default")
                label = meta.get("label", "")
                active = meta.get("active", True)
                
                from app.platform.db.stores import ensure_org
                ensure_org(org_id)
                
                with db_cursor() as cur:
                    cur.execute("SELECT 1 FROM api_keys WHERE key_id = %s", (key_id,))
                    if not cur.fetchone():
                        cur.execute(
                            """
                            INSERT INTO api_keys (key_id, org_id, label, active, created_at)
                            VALUES (%s, %s, %s, %s, NOW())
                            """,
                            (key_id, org_id, label, active)
                        )
            keys_path.rename(keys_path.with_name("api_keys.json.migrated"))
            logger.info("api_keys_json_migrated_successfully")
        except Exception as e:
            logger.warning("api_keys_migration_failed", error=str(e))

    # 2. Usage monthly migration
    usage_path = data_path("usage_meter.json")
    if usage_path.exists():
        try:
            data = json.loads(usage_path.read_text(encoding="utf-8"))
            for org_id, monthly_data in data.items():
                if org_id == "metrics":
                    continue
                from app.platform.db.stores import ensure_org
                ensure_org(org_id)
                for month_key, metrics in monthly_data.items():
                    for metric, count in metrics.items():
                        with db_cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO usage_monthly (org_id, month_key, metric, count)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (org_id, month_key, metric)
                                DO NOTHING
                                """,
                                (org_id, month_key, metric, count)
                            )
            usage_path.rename(usage_path.with_name("usage_meter.json.migrated"))
            logger.info("usage_meter_json_migrated_successfully")
        except Exception as e:
            logger.warning("usage_meter_migration_failed", error=str(e))

    # 3. Audit log migration
    audit_path = data_path("audit_log.jsonl")
    if audit_path.exists():
        try:
            with audit_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    org_id = event.get("org_id", "default")
                    action = event.get("action", "")
                    actor = event.get("actor", "")
                    res_type = event.get("resource_type", "")
                    res_id = event.get("resource_id", "")
                    details = event.get("details", {})
                    if "correlation_id" in event:
                        details["correlation_id"] = event["correlation_id"]
                    
                    from app.platform.db.stores import ensure_org
                    ensure_org(org_id)
                    with db_cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO audit_events (org_id, action, actor, resource_type, resource_id, details)
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (org_id, action, actor, res_type, res_id, json.dumps(details))
                        )
            audit_path.rename(audit_path.with_name("audit_log.jsonl.migrated"))
            logger.info("audit_log_jsonl_migrated_successfully")
        except Exception as e:
            logger.warning("audit_log_migration_failed", error=str(e))
