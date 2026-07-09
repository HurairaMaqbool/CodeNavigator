# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/tenant_context.py
------------------------------
Request-scoped organization (tenant) context for multi-tenant isolation.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

DEFAULT_ORG_ID = "default"

_org_id: ContextVar[str] = ContextVar("org_id", default=DEFAULT_ORG_ID)
_api_key_label: ContextVar[str] = ContextVar("api_key_label", default="")


@dataclass(frozen=True)
class TenantContext:
    org_id: str
    api_key_label: str = ""


def set_tenant(org_id: str, *, api_key_label: str = "") -> None:
    _org_id.set(org_id or DEFAULT_ORG_ID)
    _api_key_label.set(api_key_label or "")


def get_tenant() -> TenantContext:
    return TenantContext(org_id=_org_id.get(), api_key_label=_api_key_label.get())


def require_org_access(record_org_id: str | None) -> None:
    """Raise PermissionError if record belongs to another org."""
    tenant_org = get_tenant().org_id
    if not isinstance(record_org_id, str) or not record_org_id.strip():
        effective = DEFAULT_ORG_ID
    else:
        effective = record_org_id
    if effective != tenant_org:
        raise PermissionError(
            f"Repository belongs to org {effective!r}, not {tenant_org!r}"
        )
