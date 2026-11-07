from __future__ import annotations

import calendar as pycalendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..domain.calculation import (
    ContractSegment,
    Distribution,
    MonthCalculationInput,
    calculate_month,
    weighted_average_hours,
    workload_band,
)
from ..models import (
    AssignmentCatalog,
    AssignmentRequest,
    ContractVersion,
    DistributionParameter,
    InstitutionalCalendar,
    MonthlyPlanning,
    SystemParameter,
    Unavailability,
)


def _overlaps_month(start: dt.date, end: dt.date | None, year: int, month: int) -> bool:
    month_start = dt.date(year, month, 1)
    month_end = dt.date(year, month, pycalendar.monthrange(year, month)[1])
    return start <= month_end and (end is None or end >= month_start)


def _month_contract_values(contracts: list[ContractVersion], year: int, month: int) -> tuple[Decimal, Decimal, ContractVersion]:
    days = pycalendar.monthrange(year, month)[1]
    month_start = dt.date(year, month, 1)
    month_end = dt.date(year, month, days)
    total_weighted = Decimal("0")
    active_dates: set[dt.date] = set()
    latest = max(contracts, key=lambda item: item.effective_from)
    for item in contracts:
        first = max(month_start, item.effective_from)
        last = min(month_end, item.effective_to or month_end)
        if first > last:
            continue
        count = (last - first).days + 1
        total_weighted += Decimal(item.weekly_hours) * count
        active_dates.update(first + dt.timedelta(days=offset) for offset in range(count))
        if item.effective_from >= latest.effective_from:
            latest = item
    if not active_dates:
        return Decimal("0"), Decimal("0"), latest
    return total_weighted / Decimal(len(active_dates)), Decimal(len(active_dates)) / Decimal(days), latest


def _target_pct(db: Session, on_date: dt.date) -> Decimal:
    row = db.scalar(
        select(SystemParameter)
        .where(
            SystemParameter.code == "META_GESTION",
            SystemParameter.valid_from <= on_date,
            or_(SystemParameter.valid_to.is_(None), SystemParameter.valid_to >= on_date),
        )
        .order_by(SystemParameter.valid_from.desc())
    )
    return Decimal(str(row.value["value"])) if row else Decimal("0.90")


def _assignment_hours(db: Session, professional_id: str, institute: str, year: int, month: int) -> Decimal:
    month_start = dt.date(year, month, 1)
    month_end = dt.date(year, month, pycalendar.monthrange(year, month)[1])
    rows = db.execute(
        select(AssignmentCatalog.weekly_hours)
        .join(AssignmentRequest, AssignmentRequest.catalog_id == AssignmentCatalog.id)
        .where(
            AssignmentRequest.professional_id == professional_id,
            AssignmentRequest.institute_code == institute,
            AssignmentRequest.status == "approved",
            AssignmentRequest.valid_from <= month_end,
            or_(AssignmentRequest.valid_to.is_(None), AssignmentRequest.valid_to >= month_start),
        )
    ).scalars()
    return sum((Decimal(value) for value in rows if value is not None), Decimal("0"))


def recalculate(
    db: Session,
    *,
    professional_id: str | None = None,
    institute_code: str | None = None,
    year: int = 2026,
    from_month: int = 1,
) -> dict:
    filters = [ContractVersion.effective_from <= dt.date(year, 12, 31)]
    filters.append(or_(ContractVersion.effective_to.is_(None), ContractVersion.effective_to >= dt.date(year, 1, 1)))
    if professional_id:
        filters.append(ContractVersion.professional_id == professional_id)
    if institute_code:
        filters.append(ContractVersion.institute_code == institute_code)
    contracts = list(db.scalars(select(ContractVersion).where(*filters)))
    by_link: dict[tuple[str, str], list[ContractVersion]] = defaultdict(list)
    by_person: dict[str, list[ContractVersion]] = defaultdict(list)
    for contract in contracts:
        by_link[(contract.professional_id, contract.institute_code)].append(contract)
        by_person[contract.professional_id].append(contract)

    calculated = 0
    skipped: list[dict[str, object]] = []
    for (person_id, institute), link_contracts in by_link.items():
        average = weighted_average_hours(
            [ContractSegment(Decimal(c.weekly_hours), c.effective_from, c.effective_to) for c in by_person[person_id]], year
        )
        band = workload_band(average)
        for month in range(from_month, 13):
            active = [c for c in link_contracts if _overlaps_month(c.effective_from, c.effective_to, year, month)]
            if not active:
                continue
            weekly_hours, active_fraction, current_contract = _month_contract_values(active, year, month)
            on_date = dt.date(year, month, 1)
            calendar_row = db.scalar(
                select(InstitutionalCalendar).where(
                    InstitutionalCalendar.institute_code == institute,
                    InstitutionalCalendar.year == year,
                    InstitutionalCalendar.month == month,
                )
            )
            parameter = db.scalar(
                select(DistributionParameter)
                .where(
                    DistributionParameter.role == current_contract.role,
                    DistributionParameter.workload_band == band,
                    DistributionParameter.valid_from <= on_date,
                    or_(DistributionParameter.valid_to.is_(None), DistributionParameter.valid_to >= on_date),
                )
                .order_by(DistributionParameter.valid_from.desc())
            )
            if not calendar_row or not parameter:
                skipped.append(
                    {
                        "personaId": person_id,
                        "instituto": institute,
                        "mes": month,
                        "motivo": "CALENDARIO_FALTANTE" if not calendar_row else "MATRIZ_FALTANTE",
                    }
                )
                continue
            absence_days = db.scalar(
                select(func.coalesce(func.sum(Unavailability.days), 0)).where(
                    Unavailability.professional_id == person_id,
                    Unavailability.institute_code == institute,
                    Unavailability.year == year,
                    Unavailability.month == month,
                )
            ) or Decimal("0")
            distribution = Distribution(
                direct_pct=Decimal(parameter.direct_pct),
                indirect_pct=Decimal(parameter.indirect_pct),
                nas_pct=Decimal(parameter.nas_pct),
                direct_minutes=parameter.direct_minutes,
                indirect_minutes=parameter.indirect_minutes,
                group_pct=Decimal(parameter.group_pct),
                group_size=Decimal(parameter.group_size),
            )
            result = calculate_month(
                MonthCalculationInput(
                    year=year,
                    month=month,
                    weekly_hours=weekly_hours,
                    weighted_average_hours=average,
                    working_days=Decimal(calendar_row.working_days),
                    active_fraction=active_fraction,
                    absence_days=Decimal(absence_days),
                    approved_assignment_hours=_assignment_hours(db, person_id, institute, year, month),
                    distribution=distribution,
                    target_pct=_target_pct(db, on_date),
                )
            )
            existing = db.scalar(
                select(MonthlyPlanning).where(
                    MonthlyPlanning.professional_id == person_id,
                    MonthlyPlanning.institute_code == institute,
                    MonthlyPlanning.year == year,
                    MonthlyPlanning.month == month,
                )
            )
            row = existing or MonthlyPlanning(
                professional_id=person_id,
                institute_code=institute,
                year=year,
                month=month,
            )
            row.role = current_contract.role
            row.area = current_contract.area
            row.workload_band = result.workload_band
            row.contracted_hours = result.contracted_hours
            row.direct_hours = result.direct_hours
            row.indirect_hours = result.indirect_hours
            row.nas_hours = result.nas_hours
            row.absence_hours = result.absence_hours
            row.planned_direct = result.planned_direct
            row.planned_indirect = result.planned_indirect
            row.planned_total = result.planned_total
            row.target_total = result.target_total
            row.foja = result.foja
            row.parameters_version = f"{parameter.id}:{calendar_row.id}:meta-{_target_pct(db, on_date)}"
            row.calculated_at = dt.datetime.now(dt.timezone.utc)
            db.add(row)
            calculated += 1
    db.flush()
    return {"calculados": calculated, "omitidos": skipped}


def build_month_input(
    db: Session, professional_id: str, institute_code: str, year: int, month: int
) -> tuple[MonthCalculationInput, DistributionParameter, ContractVersion]:
    link_contracts = list(
        db.scalars(
            select(ContractVersion).where(
                ContractVersion.professional_id == professional_id,
                ContractVersion.institute_code == institute_code,
                ContractVersion.effective_from <= dt.date(year, month, pycalendar.monthrange(year, month)[1]),
                or_(ContractVersion.effective_to.is_(None), ContractVersion.effective_to >= dt.date(year, month, 1)),
            )
        )
    )
    if not link_contracts:
        raise ValueError("No existe contrato vigente para el período")
    all_contracts = list(
        db.scalars(
            select(ContractVersion).where(
                ContractVersion.professional_id == professional_id,
                ContractVersion.effective_from <= dt.date(year, 12, 31),
                or_(ContractVersion.effective_to.is_(None), ContractVersion.effective_to >= dt.date(year, 1, 1)),
            )
        )
    )
    average = weighted_average_hours(
        [ContractSegment(Decimal(c.weekly_hours), c.effective_from, c.effective_to) for c in all_contracts], year
    )
    weekly_hours, active_fraction, current = _month_contract_values(link_contracts, year, month)
    on_date = dt.date(year, month, 1)
    calendar_row = db.scalar(
        select(InstitutionalCalendar).where(
            InstitutionalCalendar.institute_code == institute_code,
            InstitutionalCalendar.year == year,
            InstitutionalCalendar.month == month,
        )
    )
    if not calendar_row:
        raise ValueError("No existe calendario para el período")
    parameter = db.scalar(
        select(DistributionParameter)
        .where(
            DistributionParameter.role == current.role,
            DistributionParameter.workload_band == workload_band(average),
            DistributionParameter.valid_from <= on_date,
            or_(DistributionParameter.valid_to.is_(None), DistributionParameter.valid_to >= on_date),
        )
        .order_by(DistributionParameter.valid_from.desc())
    )
    if not parameter:
        raise ValueError("No existe matriz de distribución aplicable")
    absence_days = db.scalar(
        select(func.coalesce(func.sum(Unavailability.days), 0)).where(
            Unavailability.professional_id == professional_id,
            Unavailability.institute_code == institute_code,
            Unavailability.year == year,
            Unavailability.month == month,
        )
    ) or Decimal("0")
    return (
        MonthCalculationInput(
            year=year,
            month=month,
            weekly_hours=weekly_hours,
            weighted_average_hours=average,
            working_days=Decimal(calendar_row.working_days),
            active_fraction=active_fraction,
            absence_days=Decimal(absence_days),
            approved_assignment_hours=_assignment_hours(db, professional_id, institute_code, year, month),
            distribution=Distribution(
                direct_pct=Decimal(parameter.direct_pct),
                indirect_pct=Decimal(parameter.indirect_pct),
                nas_pct=Decimal(parameter.nas_pct),
                direct_minutes=parameter.direct_minutes,
                indirect_minutes=parameter.indirect_minutes,
                group_pct=Decimal(parameter.group_pct),
                group_size=Decimal(parameter.group_size),
            ),
            target_pct=_target_pct(db, on_date),
        ),
        parameter,
        current,
    )


def planning_to_dict(row: MonthlyPlanning) -> dict:
    return {
        "personaId": row.professional_id,
        "instituto": row.institute_code,
        "cargo": row.role,
        "area": row.area,
        "anio": row.year,
        "mes": row.month,
        "tramo": row.workload_band,
        "horasContratadas": float(row.contracted_hours),
        "horasDirectas": float(row.direct_hours),
        "horasIndirectas": float(row.indirect_hours),
        "horasNas": float(row.nas_hours),
        "horasAusencia": float(row.absence_hours),
        "atencionesDirectas": row.planned_direct,
        "atencionesIndirectas": row.planned_indirect,
        "atencionesPlanificadas": row.planned_total,
        "metaGestion": row.target_total,
        "foja": float(row.foja) if row.foja is not None else None,
        "versionParametros": row.parameters_version,
    }
