# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.platform.db.stores import (
    ensure_org,
    pg_resolve_api_key,
    pg_create_api_key,
    pg_list_api_keys,
    pg_revoke_api_key,
    pg_increment_usage,
    pg_get_usage,
    pg_get_subscription,
    pg_set_subscription,
    pg_record_audit,
    pg_read_audit,
    use_postgres,
)


@pytest.fixture
def mock_cur():
    with patch("app.platform.db.stores.db_cursor") as mock_cursor:
        cur = MagicMock()
        mock_cursor.return_value.__enter__.return_value = cur
        yield cur


def test_use_postgres():
    with patch("app.platform.db.stores.postgres_enabled", return_value=True):
        assert use_postgres() is True
    with patch("app.platform.db.stores.postgres_enabled", return_value=False):
        assert use_postgres() is False


def test_ensure_org(mock_cur):
    ensure_org("org123")
    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "INSERT INTO organizations" in sql
    assert params == ("org123", "org123")


def test_pg_resolve_api_key_hit(mock_cur):
    mock_cur.fetchone.return_value = ("org123", "my-key-label", "key_abc_123456789")
    res = pg_resolve_api_key("key_abc_123456789")
    assert res == {"org_id": "org123", "label": "my-key-label", "key_id": "key_abc_1234"}
    mock_cur.execute.assert_called_once()


def test_pg_resolve_api_key_miss(mock_cur):
    mock_cur.fetchone.return_value = None
    res = pg_resolve_api_key("nonexistent")
    assert res is None


def test_pg_create_api_key(mock_cur):
    pg_create_api_key("org123", "key-label", "secret_key_123")
    # should call ensure_org first, then insert key
    assert mock_cur.execute.call_count == 2
    sql1, params1 = mock_cur.execute.call_args_list[0][0]
    sql2, params2 = mock_cur.execute.call_args_list[1][0]
    assert "INSERT INTO organizations" in sql1
    assert "INSERT INTO api_keys" in sql2
    assert params2 == ("secret_key_123", "org123", "key-label")


def test_pg_list_api_keys(mock_cur):
    now = datetime.now(timezone.utc)
    mock_cur.fetchall.return_value = [
        ("key_abc_123", "org123", "label1", True, now),
        ("key_xyz_456", "org123", "label2", False, None),
    ]
    res = pg_list_api_keys("org123")
    assert len(res) == 2
    assert res[0]["key_prefix"] == "key_abc_…"
    assert res[0]["org_id"] == "org123"
    assert res[0]["label"] == "label1"
    assert res[0]["active"] is True
    assert res[0]["created_at"] == now.isoformat()
    assert res[1]["created_at"] is None

    # test list all (no org_id)
    mock_cur.execute.reset_mock()
    pg_list_api_keys()
    mock_cur.execute.assert_called_once()
    sql = mock_cur.execute.call_args[0][0]
    assert "WHERE org_id" not in sql


def test_pg_revoke_api_key(mock_cur):
    mock_cur.rowcount = 1
    res = pg_revoke_api_key("org123", "key_abc_…")
    assert res is True
    sql, params = mock_cur.execute.call_args[0]
    assert "UPDATE api_keys SET active = FALSE" in sql
    assert params == ("org123", "key_abc_%")


def test_pg_increment_usage(mock_cur):
    mock_cur.fetchone.return_value = (5,)
    mock_cur.fetchall.return_value = [("chat", 5), ("ingest", 2)]
    res = pg_increment_usage("org123", "2026-07", "chat", 1)
    assert res == {"chat": 5, "ingest": 2}
    assert mock_cur.execute.call_count == 3  # ensure_org, upsert, list-all


def test_pg_get_usage(mock_cur):
    mock_cur.fetchall.return_value = [("chat", 10)]
    res = pg_get_usage("org123", "2026-07")
    assert res == {"chat": 10}


def test_pg_get_subscription_hit(mock_cur):
    now = datetime.now(timezone.utc)
    mock_cur.fetchone.return_value = ("org123", "pro", "active", "cus_123", "sub_456", now)
    res = pg_get_subscription("org123")
    assert res["plan_id"] == "pro"
    assert res["status"] == "active"
    assert res["stripe_customer_id"] == "cus_123"
    assert res["stripe_subscription_id"] == "sub_456"
    assert res["updated_at"] == now.isoformat()


def test_pg_get_subscription_miss(mock_cur):
    mock_cur.fetchone.return_value = None
    res = pg_get_subscription("org123")
    assert res["plan_id"] == "free"
    assert res["status"] == "active"


def test_pg_set_subscription(mock_cur):
    # Retrieve mock_cur configuration for mock nested call to pg_get_subscription
    mock_cur.fetchone.return_value = ("org123", "pro", "active", "cus_123", "sub_456", None)
    
    res = pg_set_subscription(
        "org123",
        plan_id="pro",
        status="active",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_456",
    )
    assert res["plan_id"] == "pro"
    # pg_set_subscription execution flow:
    #   1. ensure_org(org_id)         → 1 execute (INSERT … ON CONFLICT DO NOTHING)
    #   2. UPDATE organizations …     → 1 execute
    #   3. pg_get_subscription calls ensure_org → 1 execute
    #   4. pg_get_subscription SELECT → 1 execute
    assert mock_cur.execute.call_count == 4


def test_pg_record_audit(mock_cur):
    pg_record_audit(
        "api_key_create",
        org_id="org123",
        actor="admin",
        resource_type="api_key",
        resource_id="key123",
        details={"ip": "127.0.0.1"},
    )
    assert mock_cur.execute.call_count == 2
    sql = mock_cur.execute.call_args_list[1][0][0]
    assert "INSERT INTO audit_events" in sql


def test_pg_read_audit(mock_cur):
    now = datetime.now(timezone.utc)
    mock_cur.fetchall.return_value = [
        (now, "api_key_create", "org123", "admin", "api_key", "key123", {"ip": "127.0.0.1"})
    ]
    res = pg_read_audit("org123", limit=10)
    assert len(res) == 1
    assert res[0]["action"] == "api_key_create"
    assert res[0]["actor"] == "admin"
    assert res[0]["timestamp"] == now.isoformat()
    assert res[0]["details"] == {"ip": "127.0.0.1"}

    # read all (no org_id)
    mock_cur.execute.reset_mock()
    pg_read_audit(None, limit=10)
    mock_cur.execute.assert_called_once()
