from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import AssignmentCatalog, AssignmentRequest, ContractVersion
from ..schemas import AssignmentRequestInput, Principal
from .common import audit
from .planning import recalculate


class AssignmentRuleError(ValueError):
    pass


def _weekly_hours(db: Session, person_id: str, on_date: dt.date) -> Decimal:
    values = db.scalars(
        select(ContractVersion.weekly_hours).where(
            ContractVersion.professional_id == person_id,
            ContractVersion.effective_from <= on_date,
            or_(ContractVersion.effective_to.is_(None), ContractVersion.effective_to >= on_date),
        )
    )
    return sum((Decimal(value) for value in values), Decimal("0"))


def _overlap_count(db: Session, payload: AssignmentRequestInput, exclude_id: str | None = None) -> int:
    end = payload.valid_to or dt.date.max
    query = select(func.count()).select_from(AssignmentRequest).where(
        AssignmentRequest.professional_id == payload.professional_id,
        AssignmentRequest.status == "approved",
        AssignmentRequest.valid_from <= end,
        or_(AssignmentRequest.valid_to.is_(None), AssignmentRequest.valid_to >= payload.valid_from),
    )
    if exclude_id:
        query = query.where(AssignmentRequest.id != exclude_id)
    return int(db.scalar(query) or 0)


def validate_limit(db: Session, payload: AssignmentRequestInput, exclude_id: str | None = None) -> None:
    if _weekly_hours(db, payload.professional_id, payload.valid_from) > Decimal("30"):
        if _overlap_count(db, payload, exclude_id) >= 2:
            raise AssignmentRuleError(
                "Profesionales con jornada superior a 30 horas no pueden tener más de dos asignaciones simultáneas"
            )


def create_request(db: Session, payload: AssignmentRequestInput, principal: Principal) -> AssignmentRequest:
    catalog = db.get(AssignmentCatalog, payload.catalog_id)
    if not catalog or not catalog.active:
        raise AssignmentRuleError("Asignación inexistente o inactiva")
    status = "pending" if catalog.requires_dmn else "approved"
    if status == "approved":
        validate_limit(db, payload)
    row = AssignmentRequest(
        professional_id=payload.professional_id,
        institute_code=payload.institute_code,
        catalog_id=payload.catalog_id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        status=status,
        requested_by=principal.actor_id,
        requested_reason=payload.reason,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        principal,
        "assignment_requested",
        "assignment_request",
        row.id,
        new_value={"status": status, "catalogId": catalog.id},
        justification=payload.reason,
    )
    if status == "approved":
        recalculate(
            db,
            professional_id=row.professional_id,
            institute_code=row.institute_code,
            year=row.valid_from.year,
            from_month=row.valid_from.month,
        )
    return row


def decide_request(
    db: Session, request_id: str, approve: bool, reason: str, principal: Principal
) -> AssignmentRequest:
    row = db.get(AssignmentRequest, request_id)
    if not row or row.status != "pending":
        raise AssignmentRuleError("La solicitud no existe o ya fue resuelta")
    if approve:
        validate_limit(
            db,
            AssignmentRequestInput(
                personaId=row.professional_id,
                instituto=row.institute_code,
                asignacionId=row.catalog_id,
                vigenteDesde=row.valid_from,
                vigenteHasta=row.valid_to,
                justificacion=row.requested_reason,
            ),
            exclude_id=row.id,
        )
    old = {"status": row.status}
    row.status = "approved" if approve else "rejected"
    row.decided_by = principal.actor_id
    row.decision_reason = reason
    row.decided_at = dt.datetime.now(dt.timezone.utc)
    audit(
        db,
        principal,
        "assignment_approved" if approve else "assignment_rejected",
        "assignment_request",
        row.id,
        old_value=old,
        new_value={"status": row.status},
        justification=reason,
    )
    if approve:
        recalculate(
            db,
            professional_id=row.professional_id,
            institute_code=row.institute_code,
            year=row.valid_from.year,
            from_month=row.valid_from.month,
        )
    db.flush()
    return row
