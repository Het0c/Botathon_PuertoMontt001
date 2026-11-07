import datetime as dt
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.auth import user_principal
from backend.models import (
    AssignmentCatalog,
    AssignmentRequest,
    AuditEvent,
    ContractVersion,
    ImportBatch,
    MonthlyPlanning,
    SicActual,
)
from backend.schemas import (
    AssignmentRequestInput,
    BukRecord,
    ContractDelta,
    ImportCreate,
    Principal,
    Role,
    SicRecord,
)
from backend.services.assignments import AssignmentRuleError, create_request, decide_request
from backend.services.imports import ImportConflict, complete_import, create_import, stage_deltas, stage_records
from backend.services.planning import build_month_input, recalculate


def buk_record(source_id="buk-1", hours=40):
    return {
        "sourceRecordId": source_id,
        "personaId": "137732",
        "instituto": "Ari",
        "cargo": "MEDICO FISIATRA",
        "regSic": "D - SIC",
        "contrato": {"fechaInicio": "2025-07-01", "horasSemanales": hours},
        "meses": {"01": {"licencias": 0, "vacaciones": 0}, "02": {"licencias": 0, "vacaciones": 3}},
    }


def import_buk(db, rpa, key="buk-enero"):
    batch, _ = create_import(
        db,
        ImportCreate(source="BUK", filename="Nac - Base contratos x mes.xlsx", fileHash="a" * 64, idempotencyKey=key),
        rpa,
    )
    stage_records(db, batch, [buk_record()])
    result = complete_import(db, batch, 1, rpa)
    db.commit()
    return batch, result


def test_blue_prism_json_contract_filters_reg_sic():
    data = buk_record()
    data["regSic"] = "OTRO"
    with pytest.raises(Exception):
        BukRecord.model_validate(data)


def test_full_buk_flow_persists_and_calculates(configured_db, rpa):
    batch, result = import_buk(configured_db, rpa)
    assert result["estado"] == "completed"
    assert result["recalculos"][0]["calculados"] == 12
    assert configured_db.scalar(select(func.count()).select_from(MonthlyPlanning)) == 12
    february = configured_db.scalar(select(MonthlyPlanning).where(MonthlyPlanning.month == 2))
    assert february.absence_hours > 0
    assert configured_db.scalar(select(func.count()).select_from(AuditEvent)) >= 2


def test_repeated_import_key_is_idempotent(configured_db, rpa):
    first, _ = create_import(
        configured_db,
        ImportCreate(source="BUK", filename="buk.xlsx", fileHash="b" * 64, idempotencyKey="same-key"),
        rpa,
    )
    second, created = create_import(
        configured_db,
        ImportCreate(source="BUK", filename="buk.xlsx", fileHash="b" * 64, idempotencyKey="same-key"),
        rpa,
    )
    assert not created and first.id == second.id


def test_idempotency_key_cannot_be_reused_for_another_file(configured_db, rpa):
    create_import(
        configured_db,
        ImportCreate(source="BUK", filename="a.xlsx", fileHash="a" * 64, idempotencyKey="collision"),
        rpa,
    )
    with pytest.raises(ImportConflict):
        create_import(
            configured_db,
            ImportCreate(source="BUK", filename="b.xlsx", fileHash="b" * 64, idempotencyKey="collision"),
            rpa,
        )


def test_completion_rejects_mismatched_blue_prism_count(configured_db, rpa):
    batch, _ = create_import(
        configured_db,
        ImportCreate(source="BUK", filename="buk.xlsx", fileHash="c" * 64, idempotencyKey="count-test"),
        rpa,
    )
    stage_records(configured_db, batch, [buk_record()])
    with pytest.raises(ImportConflict):
        complete_import(configured_db, batch, 2, rpa)


def test_delta_with_retroactive_effective_date_recalculates(configured_db, rpa):
    import_buk(configured_db, rpa)
    batch, _ = create_import(
        configured_db,
        ImportCreate(source="BUK", filename="delta.json", fileHash="d" * 64, idempotencyKey="delta-001"),
        rpa,
    )
    delta = ContractDelta.model_validate(
        {
            "sourceRecordId": "delta-hours-may",
            "personaId": "137732",
            "tipoCambio": "CAMBIO_HORAS",
            "fechaEfectiva": "2026-05-15",
            "valorAnterior": {"horasSemanales": 40},
            "valorNuevo": {"horasSemanales": 30},
            "justificacion": "Cambio informado por BUK",
        }
    )
    stage_deltas(configured_db, batch, [delta])
    complete_import(configured_db, batch, 1, rpa)
    configured_db.commit()
    contracts = list(configured_db.scalars(select(ContractVersion).order_by(ContractVersion.effective_from)))
    assert contracts[0].effective_to == dt.date(2026, 5, 14)
    may = configured_db.scalar(select(MonthlyPlanning).where(MonthlyPlanning.month == 5))
    june = configured_db.scalar(select(MonthlyPlanning).where(MonthlyPlanning.month == 6))
    assert may.contracted_hours > june.contracted_hours


def test_sic_zero_is_distinct_from_missing_report(configured_db, rpa):
    import_buk(configured_db, rpa)
    batch, _ = create_import(
        configured_db,
        ImportCreate(source="SIC", filename="sic.xlsx", fileHash="e" * 64, idempotencyKey="sic-0001"),
        rpa,
    )
    record = SicRecord.model_validate(
        {
            "sourceRecordId": "sic-row-1",
            "personaId": "137732",
            "instituto": "Ari",
            "year": 2026,
            "month": 1,
            "atencionesDirectas": 0,
            "atencionesIndirectas": 0,
            "reporteValidado": True,
        }
    )
    stage_records(configured_db, batch, [record.model_dump(mode="json", by_alias=True)])
    complete_import(configured_db, batch, 1, rpa)
    configured_db.commit()
    actual = configured_db.scalar(select(SicActual))
    assert actual is not None and actual.executed_direct == 0 and actual.validated_report
    assert configured_db.scalar(select(SicActual).where(SicActual.month == 2)) is None


def test_pending_dmn_assignment_does_not_affect_calculation(configured_db, rpa, rrhh):
    import_buk(configured_db, rpa)
    before, _, _ = build_month_input(configured_db, "137732", "Ari", 2026, 1)
    catalog = AssignmentCatalog(
        name="Líder de equipo",
        weekly_hours=Decimal("2"),
        active=True,
        requires_dmn=True,
        valid_from=dt.date(2026, 1, 1),
    )
    configured_db.add(catalog)
    configured_db.flush()
    request = create_request(
        configured_db,
        AssignmentRequestInput(
            personaId="137732",
            instituto="Ari",
            asignacionId=catalog.id,
            vigenteDesde="2026-01-01",
            justificacion="Responsabilidad de equipo",
        ),
        rrhh,
    )
    after, _, _ = build_month_input(configured_db, "137732", "Ari", 2026, 1)
    assert request.status == "pending"
    assert before.approved_assignment_hours == after.approved_assignment_hours == 0


def test_dmn_approval_applies_assignment_and_audits(configured_db, rpa, rrhh, dmn):
    import_buk(configured_db, rpa)
    catalog = AssignmentCatalog(
        name="Tutor docente",
        weekly_hours=Decimal("1"),
        active=True,
        requires_dmn=True,
        valid_from=dt.date(2026, 1, 1),
    )
    configured_db.add(catalog)
    configured_db.flush()
    request = create_request(
        configured_db,
        AssignmentRequestInput(
            personaId="137732",
            instituto="Ari",
            asignacionId=catalog.id,
            vigenteDesde="2026-01-01",
            justificacion="Tutoría institucional",
        ),
        rrhh,
    )
    decide_request(configured_db, request.id, True, "Aprobado por DMN", dmn)
    configured_db.commit()
    data, _, _ = build_month_input(configured_db, "137732", "Ari", 2026, 1)
    assert data.approved_assignment_hours == Decimal("1.00")
    assert configured_db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "assignment_approved")) == 1


def test_rejected_assignment_never_discounted(configured_db, rpa, rrhh, dmn):
    import_buk(configured_db, rpa)
    catalog = AssignmentCatalog(
        name="Comité paritario",
        weekly_hours=Decimal("0.5"),
        active=True,
        requires_dmn=True,
        valid_from=dt.date(2026, 1, 1),
    )
    configured_db.add(catalog)
    configured_db.flush()
    request = create_request(
        configured_db,
        AssignmentRequestInput(
            personaId="137732",
            instituto="Ari",
            asignacionId=catalog.id,
            vigenteDesde="2026-01-01",
            justificacion="Solicitud de prueba",
        ),
        rrhh,
    )
    decide_request(configured_db, request.id, False, "Antecedentes insuficientes", dmn)
    data, _, _ = build_month_input(configured_db, "137732", "Ari", 2026, 1)
    assert data.approved_assignment_hours == 0


def test_more_than_two_overlapping_assignments_is_rejected_above_30_hours(configured_db, rpa, rrhh):
    import_buk(configured_db, rpa)
    for index in range(3):
        catalog = AssignmentCatalog(
            name=f"Asignación {index}",
            weekly_hours=Decimal("1"),
            active=True,
            requires_dmn=False,
            valid_from=dt.date(2026, 1, 1),
        )
        configured_db.add(catalog)
        configured_db.flush()
        payload = AssignmentRequestInput(
            personaId="137732",
            instituto="Ari",
            asignacionId=catalog.id,
            vigenteDesde="2026-01-01",
            justificacion="Asignación automática",
        )
        if index < 2:
            create_request(configured_db, payload, rrhh)
        else:
            with pytest.raises(AssignmentRuleError):
                create_request(configured_db, payload, rrhh)


def test_invalid_user_key_is_rejected(monkeypatch):
    monkeypatch.setenv("USER_API_KEY", "valid-user-key-change-this-0001")
    monkeypatch.setenv("APP_ENV", "development")
    from backend.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(HTTPException) as error:
        user_principal(authorization=None, x_api_key="wrong", x_user_id="u1", x_role=Role.RRHH)
    assert error.value.status_code == 401
    get_settings.cache_clear()
