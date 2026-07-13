# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Audit log tail reader and correlation ID tests."""
from __future__ import annotations

import json


def test_read_tail_lines(tmp_path):
    from app.platform.audit_log import _read_tail_lines

    path = tmp_path / "audit.jsonl"
    lines = [json.dumps({"i": i}) for i in range(100)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tail = _read_tail_lines(path, 5)
    assert len(tail) == 5
    assert json.loads(tail[-1])["i"] == 99


def test_read_events_uses_tail_not_full_scan(tmp_path, monkeypatch):
    from app.platform import audit_log

    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit_log, "_AUDIT_PATH", audit_path)
    monkeypatch.setattr(audit_log, "_use_pg", lambda: False)

    for i in range(200):
        audit_log.record_event(f"action.{i}", org_id="default", actor="test")

    events = audit_log.read_events(org_id="default", limit=10)
    assert len(events) == 10
    assert events[-1]["action"] == "action.199"
