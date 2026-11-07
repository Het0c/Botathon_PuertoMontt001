from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP


ZERO = Decimal("0")
FIVE = Decimal("5")


def D(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class ContractSegment:
    weekly_hours: Decimal
    effective_from: dt.date
    effective_to: dt.date | None = None


@dataclass(frozen=True)
class Distribution:
    direct_pct: Decimal
    indirect_pct: Decimal
    nas_pct: Decimal
    direct_minutes: int
    indirect_minutes: int = 30
    group_pct: Decimal = ZERO
    group_size: Decimal = Decimal("1")

    def validate(self) -> None:
        values = (self.direct_pct, self.indirect_pct, self.nas_pct, self.group_pct)
        if any(value < ZERO or value > Decimal("1") for value in values):
            raise ValueError("Los porcentajes deben estar entre 0 y 1")
        if self.direct_pct + self.indirect_pct + self.nas_pct > Decimal("1"):
            raise ValueError("La distribución supera 100%")
        if self.direct_minutes <= 0 or self.indirect_minutes <= 0 or self.group_size < 1:
            raise ValueError("Minutos y tamaño de grupo deben ser positivos")


@dataclass(frozen=True)
class MonthCalculationInput:
    year: int
    month: int
    weekly_hours: Decimal
    weighted_average_hours: Decimal
    working_days: Decimal
    active_fraction: Decimal
    absence_days: Decimal
    approved_assignment_hours: Decimal
    distribution: Distribution
    target_pct: Decimal = Decimal("0.90")


@dataclass(frozen=True)
class MonthCalculationResult:
    workload_band: str
    contracted_hours: Decimal
    direct_hours: Decimal
    indirect_hours: Decimal
    nas_hours: Decimal
    absence_hours: Decimal
    planned_direct: int
    planned_indirect: int
    planned_total: int
    target_total: int
    foja: Decimal | None


def workload_band(average_hours: Decimal) -> str:
    average_hours = D(average_hours)
    if average_hours >= Decimal("40"):
        return "T1_>=40"
    if average_hours >= Decimal("22"):
        return "T2_22-39"
    return "T3_<22"


def legal_reference_hours(on_date: dt.date) -> Decimal:
    """Referencia 2026; la tabla SQL permite reemplazarla por vigencias configuradas."""
    if on_date < dt.date(2026, 5, 1):
        return Decimal("44")
    return Decimal("42")


def overlap_days(start: dt.date, end: dt.date, segment: ContractSegment) -> int:
    seg_end = segment.effective_to or end
    first, last = max(start, segment.effective_from), min(end, seg_end)
    return max(0, (last - first).days + 1)


def weighted_average_hours(segments: list[ContractSegment], year: int) -> Decimal:
    start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    active_days = 0
    weighted = ZERO
    current = start
    while current <= end:
        hours = sum(
            segment.weekly_hours
            for segment in segments
            if segment.effective_from <= current <= (segment.effective_to or end)
        )
        if hours:
            active_days += 1
            weighted += hours
        current += dt.timedelta(days=1)
    if active_days == 0:
        return ZERO
    return weighted / D(active_days)


def month_active_fraction(segment: ContractSegment, year: int, month: int) -> Decimal:
    days = calendar.monthrange(year, month)[1]
    start, end = dt.date(year, month, 1), dt.date(year, month, days)
    return D(overlap_days(start, end, segment)) / D(days)


def floor_attentions(hours: Decimal, minutes: int) -> int:
    return int((hours * Decimal("60") / D(minutes)).to_integral_value(rounding=ROUND_FLOOR))


def calculate_month(data: MonthCalculationInput) -> MonthCalculationResult:
    data.distribution.validate()
    if not ZERO <= data.active_fraction <= Decimal("1"):
        raise ValueError("active_fraction debe estar entre 0 y 1")
    if not ZERO <= data.target_pct <= Decimal("1"):
        raise ValueError("target_pct debe estar entre 0 y 1")

    active_days = max(ZERO, data.working_days * data.active_fraction)
    absence_days = min(max(ZERO, data.absence_days), active_days)
    available_days = active_days - absence_days
    contracted_hours = data.weekly_hours * active_days / FIVE
    absence_hours = data.weekly_hours * absence_days / FIVE

    attendance_pct = data.distribution.direct_pct + data.distribution.indirect_pct
    attendance_weekly = data.weekly_hours * attendance_pct
    assignments = min(max(ZERO, data.approved_assignment_hours), attendance_weekly)
    net_attendance_weekly = attendance_weekly - assignments
    if attendance_pct:
        direct_weekly = net_attendance_weekly * data.distribution.direct_pct / attendance_pct
        indirect_weekly = net_attendance_weekly * data.distribution.indirect_pct / attendance_pct
    else:
        direct_weekly = indirect_weekly = ZERO

    direct_hours = direct_weekly * available_days / FIVE
    indirect_hours = indirect_weekly * available_days / FIVE
    nas_hours = max(ZERO, contracted_hours - absence_hours - direct_hours - indirect_hours)

    individual_hours = direct_hours * (Decimal("1") - data.distribution.group_pct)
    group_hours = direct_hours * data.distribution.group_pct
    planned_direct = floor_attentions(individual_hours, data.distribution.direct_minutes)
    planned_direct += floor_attentions(group_hours, data.distribution.direct_minutes) * int(data.distribution.group_size)
    planned_indirect = floor_attentions(indirect_hours, data.distribution.indirect_minutes)
    planned_total = planned_direct + planned_indirect
    target_total = int((D(planned_total) * data.target_pct).to_integral_value(rounding=ROUND_HALF_UP))
    foja = direct_hours / contracted_hours if contracted_hours else None

    return MonthCalculationResult(
        workload_band=workload_band(data.weighted_average_hours),
        contracted_hours=contracted_hours,
        direct_hours=direct_hours,
        indirect_hours=indirect_hours,
        nas_hours=nas_hours,
        absence_hours=absence_hours,
        planned_direct=planned_direct,
        planned_indirect=planned_indirect,
        planned_total=planned_total,
        target_total=target_total,
        foja=foja,
    )


def simulate(data: MonthCalculationInput, **changes: object) -> tuple[MonthCalculationResult, MonthCalculationResult]:
    current = calculate_month(data)
    distribution_changes = changes.pop("distribution", None)
    updated = replace(data, **changes)
    if distribution_changes:
        updated = replace(updated, distribution=replace(data.distribution, **distribution_changes))
    return current, calculate_month(updated)
