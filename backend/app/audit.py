from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent, User


def record_audit(
    db: Session,
    *,
    trace_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor: User | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        trace_id=trace_id,
        actor_user_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail_json=detail or {},
    )
    db.add(event)
    return event
