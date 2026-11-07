import datetime as dt
from decimal import Decimal

import pytest

from backend.domain.calculation import (
    ContractSegment,
    Distribution,
    MonthCalculationInput,
    calculate_month,
    floor_attentions,
    legal_reference_hours,
    month_active_fraction,
    simulate,
    weighted_average_hours,
    workload_band,
)


def base_input(**changes):
    values = dict(
        year=2026,
        month=1,
        weekly_hours=Decimal("40"),
        weighted_average_hours=Decimal("40"),
        working_days=Decimal("21"),
        active_fraction=Decimal("1"),
        absence_days=Decimal("0"),
        approved_assignment_hours=Decimal("0"),
        distribution=Distribution(
            direct_pct=Decimal("0.65"),
            indirect_pct=Decimal("0.15"),
            nas_pct=Decimal("0.20"),
            direct_minutes=40,
        ),
        target_pct=Decimal("0.90"),
    )
    values.update(changes)
    return MonthCalculationInput(**values)


def test_full_year_contract_weighted_average():
    segment = ContractSegment(Decimal("40"), dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert weighted_average_hours([segment], 2026) == Decimal("40")


def test_partial_contract_uses_only_active_period():
    segment = ContractSegment(Decimal("30"), dt.date(2026, 7, 1), dt.date(2026, 12, 31))
    assert weighted_average_hours([segment], 2026) == Decimal("30")


def test_midyear_hours_change_is_weighted():
    segments = [
        ContractSegment(Decimal("44"), dt.date(2026, 1, 1), dt.date(2026, 4, 30)),
        ContractSegment(Decimal("42"), dt.date(2026, 5, 1), dt.date(2026, 12, 31)),
    ]
    average = weighted_average_hours(segments, 2026)
    assert Decimal("42") < average < Decimal("44")


def test_change_midmonth_does_not_apply_new_hours_to_whole_month():
    old = ContractSegment(Decimal("40"), dt.date(2026, 1, 1), dt.date(2026, 5, 14))
    new = ContractSegment(Decimal("30"), dt.date(2026, 5, 15), None)
    average = weighted_average_hours([old, new], 2026)
    assert Decimal("30") < average < Decimal("40")
    assert month_active_fraction(new, 2026, 5) == Decimal("17") / Decimal("31")


def test_legal_reference_2026_44_then_42():
    assert legal_reference_hours(dt.date(2026, 4, 30)) == Decimal("44")
    assert legal_reference_hours(dt.date(2026, 5, 1)) == Decimal("42")


@pytest.mark.parametrize(
    ("hours", "expected"),
    [(Decimal("40"), "T1_>=40"), (Decimal("22"), "T2_22-39"), (Decimal("21.99"), "T3_<22")],
)
def test_workload_band_boundaries(hours, expected):
    assert workload_band(hours) == expected


def test_multi_institute_hours_are_added_without_duplicate_person_days():
    segments = [
        ContractSegment(Decimal("20"), dt.date(2026, 1, 1)),
        ContractSegment(Decimal("20"), dt.date(2026, 1, 1)),
    ]
    assert weighted_average_hours(segments, 2026) == Decimal("40")


def test_long_leave_reduces_available_hours():
    result = calculate_month(base_input(absence_days=Decimal("21")))
    assert result.direct_hours == 0
    assert result.planned_total == 0
    assert result.absence_hours == result.contracted_hours


def test_approved_assignment_reduces_attendance_without_double_nas_discount():
    normal = calculate_month(base_input())
    assigned = calculate_month(base_input(approved_assignment_hours=Decimal("2")))
    assert assigned.direct_hours < normal.direct_hours
    assert assigned.nas_hours > normal.nas_hours
    assert assigned.direct_hours + assigned.indirect_hours + assigned.nas_hours == assigned.contracted_hours


def test_attentions_always_round_down():
    assert floor_attentions(Decimal("1.99"), 60) == 1
    result = calculate_month(base_input(working_days=Decimal("1")))
    assert isinstance(result.planned_direct, int)


def test_group_factor_only_multiplies_group_portion():
    regular = calculate_month(base_input())
    grouped = calculate_month(
        base_input(
            distribution=Distribution(
                direct_pct=Decimal("0.65"),
                indirect_pct=Decimal("0.15"),
                nas_pct=Decimal("0.20"),
                direct_minutes=40,
                group_pct=Decimal("0.20"),
                group_size=Decimal("4"),
            )
        )
    )
    assert grouped.planned_direct > regular.planned_direct
    assert grouped.planned_direct < regular.planned_direct * 4


def test_target_is_configurable_90_percent():
    result = calculate_month(base_input())
    assert result.target_total == int(Decimal(result.planned_total) * Decimal("0.90") + Decimal("0.5"))


def test_foja_is_none_with_zero_contracted_hours():
    result = calculate_month(base_input(weekly_hours=Decimal("0"), weighted_average_hours=Decimal("0")))
    assert result.foja is None


def test_simulation_does_not_mutate_input():
    data = base_input()
    current, simulated = simulate(data, target_pct=Decimal("0.80"))
    assert current.planned_total == simulated.planned_total
    assert simulated.target_total < current.target_total
    assert data.target_pct == Decimal("0.90")


def test_invalid_distribution_is_rejected():
    with pytest.raises(ValueError):
        calculate_month(
            base_input(
                distribution=Distribution(
                    direct_pct=Decimal("0.8"),
                    indirect_pct=Decimal("0.3"),
                    nas_pct=Decimal("0.1"),
                    direct_minutes=30,
                )
            )
        )
