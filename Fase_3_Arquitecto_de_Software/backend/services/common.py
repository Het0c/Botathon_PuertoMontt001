from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent
from ..schemas import Principal


def audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    justification: str | None = None,
    correlation_id: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=principal.actor_id,
            actor_role=principal.role.value,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            justification=justification,
            origin=principal.origin,
            correlation_id=correlation_id,
        )
    )
