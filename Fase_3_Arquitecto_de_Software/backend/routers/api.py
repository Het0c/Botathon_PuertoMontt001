from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import require_roles, user_principal
from ..database import get_db
from ..domain.calculation import calculate_month, simulate
from ..models import (
    AssignmentCatalog,
    AssignmentRequest,
    AuditEvent,
    ContractVersion,
    DistributionParameter,
    InstitutionalCalendar,
    Institute,
    LegalWorkweekReference,
    MonthlyPlanning,
    Professional,
    SicActual,
    SystemParameter,
)
from ..schemas import (
    AssignmentCatalogInput,
    AssignmentDecision,
    AssignmentRequestInput,
    CalendarInput,
    DistributionInput,
    LegalReferenceInput,
    Principal,
    RecalculateRequest,
    Role,
    SimulationInput,
    TargetParameterInput,
)
from ..services.assignments import AssignmentRuleError, create_request, decide_request
from ..services.common import audit
from ..services.planning import build_month_input, planning_to_dict, recalculate


router = APIRouter(prefix="/api/v1")
write_roles = (Role.RRHH, Role.DMN)
read_roles = (Role.RRHH, Role.DMN, Role.MANAGEMENT)


@router.get("/institutos", tags=["Dotación"])
def institutes(
    principal: Principal = Depends(require_roles(*read_roles)), db: Session = Depends(get_db)
) -> list[dict]:
    del principal
    return [{"codigo": row.code, "nombre": row.name, "zona": row.zone} for row in db.scalars(select(Institute))]


@router.get("/profesionales", tags=["Dotación"])
def professionals(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(user_principal),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Professional)
    if principal.role == Role.PROFESSIONAL:
        query = query.where(Professional.id == principal.actor_id)
    elif principal.role not in read_roles:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.offset((page - 1) * size).limit(size)))
    return {"items": [{"personaId": row.id, "activa": row.active} for row in rows], "total": total}


@router.get("/profesionales/{person_id}", tags=["Dotación"])
def professional_detail(
    person_id: str,
    principal: Principal = Depends(user_principal),
    db: Session = Depends(get_db),
) -> dict:
    if principal.role == Role.PROFESSIONAL and principal.actor_id != person_id:
        raise HTTPException(status_code=403, detail="Solo puede consultar su propia información")
    if principal.role not in (*read_roles, Role.PROFESSIONAL):
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    row = db.get(Professional, person_id)
    if not row:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    return {"personaId": row.id, "activa": row.active}


@router.get("/profesionales/{person_id}/contratos", tags=["Dotación"])
def professional_contracts(
    person_id: str,
    principal: Principal = Depends(user_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    if principal.role == Role.PROFESSIONAL and principal.actor_id != person_id:
        raise HTTPException(status_code=403, detail="Solo puede consultar sus contratos")
    if principal.role not in (*read_roles, Role.PROFESSIONAL):
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    rows = db.scalars(
        select(ContractVersion)
        .where(ContractVersion.professional_id == person_id)
        .order_by(ContractVersion.effective_from)
    )
    return [
        {
            "id": row.id,
            "personaId": row.professional_id,
            "instituto": row.institute_code,
            "cargo": row.role,
            "area": row.area,
            "horasSemanales": float(row.weekly_hours),
            "fechaInicio": row.effective_from,
            "fechaTermino": row.effective_to,
        }
        for row in rows
    ]


@router.post("/parametros/distribuciones", tags=["Parámetros"], status_code=201)
def create_distribution(
    payload: DistributionInput,
    principal: Principal = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
) -> dict:
    row = DistributionParameter(
        role=payload.role.upper(),
        workload_band=payload.workload_band,
        direct_pct=payload.direct_pct,
        indirect_pct=payload.indirect_pct,
        nas_pct=payload.nas_pct,
        direct_minutes=payload.direct_minutes,
        indirect_minutes=payload.indirect_minutes,
        group_pct=payload.group_pct,
        group_size=payload.group_size,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(row)
    db.flush()
    audit(db, principal, "parameter_created", "distribution_parameter", row.id, new_value=payload.model_dump(mode="json", by_alias=True))
    db.commit()
    return {"id": row.id}


@router.get("/parametros", tags=["Parámetros"])
def parameters(
    principal: Principal = Depends(require_roles(*read_roles)), db: Session = Depends(get_db)
) -> dict:
    del principal
    distributions = list(db.scalars(select(DistributionParameter)))
    system = list(db.scalars(select(SystemParameter)))
    legal = list(db.scalars(select(LegalWorkweekReference)))
    return {
        "distribuciones": [
            {
                "id": row.id,
                "cargo": row.role,
                "tramo": row.workload_band,
                "pctDirecto": float(row.direct_pct),
                "pctIndirecto": float(row.indirect_pct),
                "pctNas": float(row.nas_pct),
                "minutosDirecta": row.direct_minutes,
                "minutosIndirecta": row.indirect_minutes,
                "vigenteDesde": row.valid_from,
                "vigenteHasta": row.valid_to,
            }
            for row in distributions
        ],
        "generales": [{"codigo": row.code, "valor": row.value, "vigenteDesde": row.valid_from} for row in system],
        "jornadaLegal": [
            {
                "horasSemanales": float(row.weekly_hours) if row.weekly_hours is not None else None,
                "vigenteDesde": row.valid_from,
                "vigenteHasta": row.valid_to,
                "descripcion": row.description,
            }
            for row in legal
        ],
    }


@router.put("/parametros/meta", tags=["Parámetros"])
def update_target(
    payload: TargetParameterInput,
    principal: Principal = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
) -> dict:
    row = SystemParameter(
        code="META_GESTION",
        value={"value": str(payload.value)},
        description="Porcentaje mínimo de meta de gestión asistencial",
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        principal,
        "parameter_created",
        "system_parameter",
        row.id,
        new_value={"value": str(payload.value)},
        justification=payload.justification,
    )
    db.commit()
    return {"id": row.id, "valor": float(payload.value)}


@router.post("/parametros/jornada-legal", tags=["Parámetros"], status_code=201)
def create_legal_reference(
    payload: LegalReferenceInput,
    principal: Principal = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
) -> dict:
    row = LegalWorkweekReference(
        weekly_hours=payload.weekly_hours,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        description=payload.description,
    )
    db.add(row)
    db.flush()
    audit(db, principal, "legal_reference_created", "legal_workweek_reference", row.id, new_value=payload.model_dump(mode="json", by_alias=True))
    db.commit()
    return {"id": row.id}


@router.post("/calendarios", tags=["Parámetros"], status_code=201)
def create_calendar(
    payload: CalendarInput,
    principal: Principal = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
) -> dict:
    institute = db.get(Institute, payload.instituto)
    if not institute:
        institute = Institute(code=payload.instituto, name=payload.institute_name or payload.instituto, zone=payload.zone)
        db.add(institute)
    row = InstitutionalCalendar(
        institute_code=payload.instituto,
        year=payload.year,
        month=payload.month,
        working_days=payload.working_days,
        national_holidays=payload.national_holidays,
        regional_holidays=payload.regional_holidays,
        special_regime_days=payload.special_regime_days,
        zone=payload.zone,
    )
    db.add(row)
    db.flush()
    audit(db, principal, "calendar_created", "institutional_calendar", row.id, new_value=payload.model_dump(mode="json", by_alias=True))
    db.commit()
    return {"id": row.id}


@router.get("/calendarios", tags=["Parámetros"])
def calendars(
    year: int = 2026,
    institute: str | None = None,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> list[dict]:
    del principal
    query = select(InstitutionalCalendar).where(InstitutionalCalendar.year == year)
    if institute:
        query = query.where(InstitutionalCalendar.institute_code == institute)
    return [
        {
            "id": row.id,
            "instituto": row.institute_code,
            "anio": row.year,
            "mes": row.month,
            "diasHabiles": float(row.working_days),
            "zona": row.zone,
        }
        for row in db.scalars(query)
    ]


@router.post("/asignaciones/catalogo", tags=["Asignaciones"], status_code=201)
def catalog_create(
    payload: AssignmentCatalogInput,
    principal: Principal = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
) -> dict:
    row = AssignmentCatalog(
        name=payload.name,
        weekly_hours=payload.weekly_hours,
        active=payload.active,
        requires_dmn=payload.requires_dmn,
        valid_from=payload.valid_from,
    )
    db.add(row)
    db.flush()
    audit(db, principal, "assignment_catalog_created", "assignment_catalog", row.id, new_value=payload.model_dump(mode="json", by_alias=True))
    db.commit()
    return {"id": row.id}


@router.get("/asignaciones", tags=["Asignaciones"])
def assignments(
    principal: Principal = Depends(require_roles(*read_roles)), db: Session = Depends(get_db)
) -> dict:
    del principal
    catalog = list(db.scalars(select(AssignmentCatalog)))
    requests = list(db.scalars(select(AssignmentRequest).order_by(AssignmentRequest.valid_from.desc())))
    return {
        "catalogo": [
            {
                "id": row.id,
                "nombre": row.name,
                "horasSemanales": float(row.weekly_hours) if row.weekly_hours is not None else None,
                "activa": row.active,
                "requiereDmn": row.requires_dmn,
            }
            for row in catalog
        ],
        "solicitudes": [
            {
                "id": row.id,
                "personaId": row.professional_id,
                "instituto": row.institute_code,
                "asignacionId": row.catalog_id,
                "estado": row.status,
                "vigenteDesde": row.valid_from,
                "vigenteHasta": row.valid_to,
            }
            for row in requests
        ],
    }


@router.get("/asignaciones/solicitudes", tags=["Asignaciones"])
def assignment_requests(
    status_filter: str | None = Query(default=None, alias="estado"),
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> list[dict]:
    del principal
    query = select(AssignmentRequest).order_by(AssignmentRequest.valid_from.desc())
    if status_filter:
        query = query.where(AssignmentRequest.status == status_filter)
    return [
        {
            "id": row.id,
            "personaId": row.professional_id,
            "instituto": row.institute_code,
            "asignacionId": row.catalog_id,
            "estado": row.status,
            "vigenteDesde": row.valid_from,
            "vigenteHasta": row.valid_to,
        }
        for row in db.scalars(query)
    ]


@router.post("/asignaciones/solicitudes", tags=["Asignaciones"], status_code=201)
def assignment_request_create(
    payload: AssignmentRequestInput,
    principal: Principal = Depends(require_roles(Role.RRHH, Role.DMN)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = create_request(db, payload, principal)
        db.commit()
        return {"id": row.id, "estado": row.status}
    except AssignmentRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _decision(request_id: str, payload: AssignmentDecision, approve: bool, principal: Principal, db: Session) -> dict:
    try:
        row = decide_request(db, request_id, approve, payload.reason, principal)
        db.commit()
        return {"id": row.id, "estado": row.status}
    except AssignmentRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/asignaciones/solicitudes/{request_id}/aprobar", tags=["Asignaciones"])
def assignment_approve(
    request_id: str,
    payload: AssignmentDecision,
    principal: Principal = Depends(require_roles(Role.DMN)),
    db: Session = Depends(get_db),
) -> dict:
    return _decision(request_id, payload, True, principal, db)


@router.post("/asignaciones/solicitudes/{request_id}/rechazar", tags=["Asignaciones"])
def assignment_reject(
    request_id: str,
    payload: AssignmentDecision,
    principal: Principal = Depends(require_roles(Role.DMN)),
    db: Session = Depends(get_db),
) -> dict:
    return _decision(request_id, payload, False, principal, db)


def _planning_query(
    institute: str | None,
    area: str | None,
    role: str | None,
    person_id: str | None,
    month: int | None,
    year: int,
):
    query = select(MonthlyPlanning).where(MonthlyPlanning.year == year)
    if institute:
        query = query.where(MonthlyPlanning.institute_code == institute)
    if area:
        query = query.where(MonthlyPlanning.area == area)
    if role:
        query = query.where(MonthlyPlanning.role == role.upper())
    if person_id:
        query = query.where(MonthlyPlanning.professional_id == person_id)
    if month:
        query = query.where(MonthlyPlanning.month == month)
    return query


@router.get("/planificacion", tags=["Planificación"])
def planning(
    institute: str | None = None,
    area: str | None = None,
    role: str | None = None,
    person_id: str | None = Query(default=None, alias="personaId"),
    month: int | None = Query(default=None, ge=1, le=12),
    year: int = 2026,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(user_principal),
    db: Session = Depends(get_db),
) -> dict:
    if principal.role == Role.PROFESSIONAL:
        person_id = principal.actor_id
    elif principal.role not in read_roles:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    query = _planning_query(institute, area, role, person_id, month, year)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.offset((page - 1) * size).limit(size)))
    return {"items": [planning_to_dict(row) for row in rows], "total": total}


@router.get("/profesionales/{person_id}/planificacion", tags=["Dotación"])
def professional_planning(
    person_id: str,
    year: int = 2026,
    month: int | None = Query(default=None, ge=1, le=12),
    principal: Principal = Depends(user_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    if principal.role == Role.PROFESSIONAL and principal.actor_id != person_id:
        raise HTTPException(status_code=403, detail="Solo puede consultar su planificación")
    if principal.role not in (*read_roles, Role.PROFESSIONAL):
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    query = _planning_query(None, None, None, person_id, month, year)
    return [planning_to_dict(row) for row in db.scalars(query)]


@router.post("/planificacion/recalcular", tags=["Planificación"])
def planning_recalculate(
    payload: RecalculateRequest,
    principal: Principal = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
) -> dict:
    result = recalculate(
        db,
        professional_id=payload.professional_id,
        institute_code=payload.institute_code,
        year=payload.year,
        from_month=payload.from_month,
    )
    audit(db, principal, "planning_recalculated", "planning", payload.professional_id or "batch", new_value=result)
    db.commit()
    return result


@router.post("/simulaciones", tags=["Planificación"])
def simulation(
    payload: SimulationInput,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    try:
        data, _, _ = build_month_input(db, payload.professional_id, payload.institute_code, payload.year, payload.month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    distribution_changes = {}
    if payload.direct_pct is not None:
        distribution_changes["direct_pct"] = payload.direct_pct
    if payload.indirect_pct is not None:
        distribution_changes["indirect_pct"] = payload.indirect_pct
    if payload.direct_minutes is not None:
        distribution_changes["direct_minutes"] = payload.direct_minutes
    changes = {"distribution": distribution_changes}
    if payload.target_pct is not None:
        changes["target_pct"] = payload.target_pct
    try:
        current, simulated = simulate(data, **changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "actual": {
            "horasDirectas": float(current.direct_hours),
            "atenciones": current.planned_total,
            "meta": current.target_total,
        },
        "simulado": {
            "horasDirectas": float(simulated.direct_hours),
            "atenciones": simulated.planned_total,
            "meta": simulated.target_total,
        },
        "diferencia": {
            "horasDirectas": float(simulated.direct_hours - current.direct_hours),
            "atenciones": simulated.planned_total - current.planned_total,
            "meta": simulated.target_total - current.target_total,
        },
        "persistido": False,
    }


@router.get("/planificacion/comparativa", tags=["Planificación"])
def comparison(
    year: int = 2026,
    institute: str | None = None,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> list[dict]:
    del principal
    query = select(MonthlyPlanning, SicActual).outerjoin(
        SicActual,
        (SicActual.professional_id == MonthlyPlanning.professional_id)
        & (SicActual.institute_code == MonthlyPlanning.institute_code)
        & (SicActual.year == MonthlyPlanning.year)
        & (SicActual.month == MonthlyPlanning.month),
    ).where(MonthlyPlanning.year == year)
    if institute:
        query = query.where(MonthlyPlanning.institute_code == institute)
    result = []
    for plan, actual in db.execute(query):
        executed = None if actual is None or not actual.validated_report else actual.executed_direct + actual.executed_indirect
        deviation = None if executed is None else executed - plan.target_total
        compliance = None if executed is None or plan.target_total == 0 else executed / plan.target_total
        result.append(
            {
                "personaId": plan.professional_id,
                "instituto": plan.institute_code,
                "anio": plan.year,
                "mes": plan.month,
                "meta": plan.target_total,
                "ejecutado": executed,
                "desviacion": deviation,
                "cumplimiento": compliance,
                "estado": "SIN_REPORTE" if executed is None else ("BAJO_META" if compliance is not None and compliance < 1 else "EN_META"),
            }
        )
    return result


def _summary(db: Session, year: int, institute: str | None = None) -> dict:
    filters = [MonthlyPlanning.year == year]
    if institute:
        filters.append(MonthlyPlanning.institute_code == institute)
    values = db.execute(
        select(
            func.coalesce(func.sum(MonthlyPlanning.contracted_hours), 0),
            func.coalesce(func.sum(MonthlyPlanning.direct_hours), 0),
            func.coalesce(func.sum(MonthlyPlanning.indirect_hours), 0),
            func.coalesce(func.sum(MonthlyPlanning.nas_hours), 0),
            func.coalesce(func.sum(MonthlyPlanning.planned_direct), 0),
            func.coalesce(func.sum(MonthlyPlanning.planned_indirect), 0),
            func.coalesce(func.sum(MonthlyPlanning.planned_total), 0),
            func.coalesce(func.sum(MonthlyPlanning.target_total), 0),
        ).where(*filters)
    ).one()
    contracted, direct, indirect, nas, planned_direct, planned_indirect, planned, target = values
    return {
        "anio": year,
        "instituto": institute,
        "horasContratadas": float(contracted),
        "horasDirectas": float(direct),
        "horasIndirectas": float(indirect),
        "horasNas": float(nas),
        "atencionesDirectas": int(planned_direct),
        "atencionesIndirectas": int(planned_indirect),
        "atencionesPlanificadas": int(planned),
        "metaGestion": int(target),
        "foja": float(direct / contracted) if contracted else None,
    }


@router.get("/dashboard/nacional", tags=["Dashboard"])
def dashboard_national(
    year: int = 2026,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    return _summary(db, year)


@router.get("/planificacion/resumen", tags=["Planificación"])
@router.get("/dashboard/indicadores", tags=["Dashboard"])
def planning_summary(
    year: int = 2026,
    institute: str | None = None,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    return _summary(db, year, institute)


@router.get("/dashboard/institutos", tags=["Dashboard"])
def dashboard_institutes(
    year: int = 2026,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> list[dict]:
    del principal
    institutes = db.scalars(select(MonthlyPlanning.institute_code).where(MonthlyPlanning.year == year).distinct())
    return [_summary(db, year, code) for code in institutes]


@router.get("/dashboard/alertas", tags=["Dashboard"])
def dashboard_alerts(
    year: int = 2026,
    principal: Principal = Depends(require_roles(*read_roles)),
    db: Session = Depends(get_db),
) -> list[dict]:
    del principal
    return [item for item in comparison(year=year, institute=None, principal=Principal(actorId="internal", role=Role.MANAGEMENT, origin="backend"), db=db) if item["estado"] == "BAJO_META"]


@router.get("/auditoria", tags=["Auditoría"])
def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_roles(Role.MANAGEMENT, Role.DMN, Role.RRHH)),
    db: Session = Depends(get_db),
) -> list[dict]:
    del principal
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit))
    return [
        {
            "id": row.id,
            "fecha": row.occurred_at,
            "actor": row.actor_id,
            "rol": row.actor_role,
            "accion": row.action,
            "entidad": row.entity_type,
            "entidadId": row.entity_id,
            "valorAnterior": row.old_value,
            "valorNuevo": row.new_value,
            "justificacion": row.justification,
            "origen": row.origin,
            "correlacionId": row.correlation_id,
        }
        for row in rows
    ]
