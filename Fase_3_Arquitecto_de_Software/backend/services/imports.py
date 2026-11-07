from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    ContractVersion,
    ImportBatch,
    ImportRecord,
    ImportValidationError,
    Institute,
    Professional,
    SicActual,
    Unavailability,
)
from ..schemas import (
    BukRecord,
    ContractDelta,
    ImportCreate,
    ImportSource,
    Principal,
    SicRecord,
    ValidationErrorInput,
)
from .common import audit
from .planning import recalculate


class ImportConflict(ValueError):
    pass


def create_import(db: Session, payload: ImportCreate, principal: Principal) -> tuple[ImportBatch, bool]:
    existing = db.scalar(select(ImportBatch).where(ImportBatch.idempotency_key == payload.idempotency_key))
    if existing:
        if existing.file_hash != payload.file_hash or existing.source != payload.source.value:
            raise ImportConflict("La clave de idempotencia ya fue usada con otro archivo")
        return existing, False
    batch = ImportBatch(
        source=payload.source.value,
        filename=payload.filename,
        file_hash=payload.file_hash,
        idempotency_key=payload.idempotency_key,
    )
    db.add(batch)
    db.flush()
    audit(
        db,
        principal,
        "import_created",
        "rpa_import",
        batch.id,
        new_value={"source": batch.source, "filename": batch.filename},
        correlation_id=batch.id,
    )
    return batch, True


def _record_error(db: Session, batch: ImportBatch, index: int, error: ValidationError) -> None:
    first = error.errors()[0]
    db.add(
        ImportValidationError(
            import_id=batch.id,
            row_number=index,
            field=".".join(str(part) for part in first.get("loc", [])) or None,
            code=str(first.get("type", "VALIDATION"))[:80],
            message=str(first.get("msg", "Registro inválido")),
        )
    )


def stage_records(db: Session, batch: ImportBatch, records: list[dict]) -> dict:
    if batch.status in {"completed", "failed"}:
        raise ImportConflict("La importación ya está cerrada")
    accepted = rejected = duplicates = 0
    model = BukRecord if batch.source == ImportSource.BUK.value else SicRecord
    for index, raw in enumerate(records, 1):
        source_id = raw.get("sourceRecordId") or raw.get("source_record_id")
        if source_id and db.scalar(
            select(ImportRecord).where(ImportRecord.import_id == batch.id, ImportRecord.source_record_id == str(source_id))
        ):
            duplicates += 1
            continue
        try:
            item = model.model_validate(raw)
        except ValidationError as exc:
            _record_error(db, batch, index, exc)
            rejected += 1
            continue
        db.add(
            ImportRecord(
                import_id=batch.id,
                source_record_id=item.source_record_id,
                record_type=batch.source.lower(),
                payload=item.model_dump(mode="json", by_alias=True),
            )
        )
        accepted += 1
    batch.rows_received += accepted + rejected
    batch.rows_accepted += accepted
    batch.rows_rejected += rejected
    batch.status = "receiving"
    db.flush()
    return {"aceptados": accepted, "rechazados": rejected, "duplicados": duplicates}


def stage_deltas(db: Session, batch: ImportBatch, deltas: list[ContractDelta]) -> dict:
    if batch.source != ImportSource.BUK.value:
        raise ImportConflict("Los deltas contractuales solo corresponden a BUK")
    accepted = duplicates = 0
    for item in deltas:
        if db.scalar(
            select(ImportRecord).where(ImportRecord.import_id == batch.id, ImportRecord.source_record_id == item.source_record_id)
        ):
            duplicates += 1
            continue
        db.add(
            ImportRecord(
                import_id=batch.id,
                source_record_id=item.source_record_id,
                record_type="delta",
                payload=item.model_dump(mode="json", by_alias=True),
            )
        )
        accepted += 1
    batch.rows_received += accepted
    batch.rows_accepted += accepted
    batch.status = "receiving"
    db.flush()
    return {"aceptados": accepted, "duplicados": duplicates}


def add_external_errors(db: Session, batch: ImportBatch, errors: list[ValidationErrorInput]) -> dict:
    if batch.status in {"completed", "failed"}:
        raise ImportConflict("La importación ya está cerrada")
    for item in errors:
        db.add(
            ImportValidationError(
                import_id=batch.id,
                row_number=item.row_number,
                field=item.field,
                code=item.code,
                message=item.message,
            )
        )
    batch.rows_received += len(errors)
    batch.rows_rejected += len(errors)
    batch.status = "receiving"
    db.flush()
    return {"registrados": len(errors)}


def _apply_buk(db: Session, batch: ImportBatch, stored: ImportRecord) -> tuple[str, str, int]:
    item = BukRecord.model_validate(stored.payload)
    institute = db.get(Institute, item.instituto)
    if not institute:
        db.add(Institute(code=item.instituto, name=item.institute_name or item.instituto))
    if not db.get(Professional, item.persona_id):
        db.add(Professional(id=item.persona_id))
    db.flush()
    existing = db.scalar(
        select(ContractVersion).where(
            ContractVersion.professional_id == item.persona_id,
            ContractVersion.institute_code == item.instituto,
            ContractVersion.effective_from == item.contrato.effective_from,
            ContractVersion.source_record_id == item.source_record_id,
        )
    )
    if not existing:
        overlap = db.scalar(
            select(ContractVersion).where(
                ContractVersion.professional_id == item.persona_id,
                ContractVersion.institute_code == item.instituto,
                ContractVersion.effective_from <= (item.contrato.effective_to or dt.date.max),
                (ContractVersion.effective_to.is_(None) | (ContractVersion.effective_to >= item.contrato.effective_from)),
            )
        )
        if overlap:
            equivalent = (
                overlap.role == item.cargo.upper()
                and Decimal(overlap.weekly_hours) == item.contrato.weekly_hours
                and overlap.effective_from == item.contrato.effective_from
                and overlap.effective_to == item.contrato.effective_to
            )
            if not equivalent:
                raise ImportConflict("El contrato BUK se superpone con una versión vigente; envíe el cambio como delta")
        else:
            db.add(
                ContractVersion(
                    professional_id=item.persona_id,
                    institute_code=item.instituto,
                    role=item.cargo.upper(),
                    area=item.area,
                    weekly_hours=item.contrato.weekly_hours,
                    effective_from=item.contrato.effective_from,
                    effective_to=item.contrato.effective_to,
                    source_record_id=item.source_record_id,
                    source_import_id=batch.id,
                )
            )
    for month_key, absence in item.meses.items():
        month = int(month_key)
        previous = list(
            db.scalars(
                select(Unavailability).where(
                    Unavailability.professional_id == item.persona_id,
                    Unavailability.institute_code == item.instituto,
                    Unavailability.year == item.planning_year,
                    Unavailability.month == month,
                    Unavailability.source_import_id == batch.id,
                )
            )
        )
        if previous:
            continue
        if absence.sick_leave_days:
            db.add(
                Unavailability(
                    professional_id=item.persona_id,
                    institute_code=item.instituto,
                    year=item.planning_year,
                    month=month,
                    kind="sick_leave",
                    days=absence.sick_leave_days,
                    source_import_id=batch.id,
                )
            )
        if absence.vacation_days:
            db.add(
                Unavailability(
                    professional_id=item.persona_id,
                    institute_code=item.instituto,
                    year=item.planning_year,
                    month=month,
                    kind="vacation",
                    days=absence.vacation_days,
                    source_import_id=batch.id,
                )
            )
    stored.applied = True
    return item.persona_id, item.instituto, item.planning_year


def _apply_sic(db: Session, batch: ImportBatch, stored: ImportRecord) -> tuple[str, str, int]:
    item = SicRecord.model_validate(stored.payload)
    if not db.get(Professional, item.persona_id) or not db.get(Institute, item.instituto):
        raise ImportConflict(f"SIC referencia profesional/instituto inexistente: {item.persona_id}/{item.instituto}")
    row = db.scalar(
        select(SicActual).where(
            SicActual.professional_id == item.persona_id,
            SicActual.institute_code == item.instituto,
            SicActual.year == item.year,
            SicActual.month == item.month,
        )
    )
    if not row:
        row = SicActual(
            professional_id=item.persona_id,
            institute_code=item.instituto,
            year=item.year,
            month=item.month,
        )
    row.executed_direct = item.executed_direct
    row.executed_indirect = item.executed_indirect
    row.validated_report = item.validated_report
    row.source_import_id = batch.id
    db.add(row)
    stored.applied = True
    return item.persona_id, item.instituto, item.year


def _active_contract(db: Session, person_id: str, effective_date: dt.date) -> ContractVersion | None:
    return db.scalar(
        select(ContractVersion)
        .where(
            ContractVersion.professional_id == person_id,
            ContractVersion.effective_from <= effective_date,
            (ContractVersion.effective_to.is_(None) | (ContractVersion.effective_to >= effective_date)),
        )
        .order_by(ContractVersion.effective_from.desc())
    )


def _apply_delta(db: Session, batch: ImportBatch, stored: ImportRecord, principal: Principal) -> tuple[str, str, int]:
    item = ContractDelta.model_validate(stored.payload)
    current = _active_contract(db, item.persona_id, item.effective_date)
    if item.change_type == "ALTA":
        if current:
            raise ImportConflict("ALTA inconsistente: ya existe contrato vigente")
        value = item.new_value or {}
        institute = str(value.get("instituto", "")).strip()
        if not institute:
            raise ImportConflict("ALTA requiere instituto")
        if not db.get(Institute, institute):
            db.add(Institute(code=institute, name=str(value.get("nombreInstituto") or institute)))
        if not db.get(Professional, item.persona_id):
            db.add(Professional(id=item.persona_id))
        db.flush()
        new_contract = ContractVersion(
            professional_id=item.persona_id,
            institute_code=institute,
            role=str(value["cargo"]).upper(),
            area=value.get("area"),
            weekly_hours=Decimal(str(value["horasSemanales"])),
            effective_from=item.effective_date,
            effective_to=dt.date.fromisoformat(value["fechaTermino"]) if value.get("fechaTermino") else None,
            source_record_id=item.source_record_id,
            source_import_id=batch.id,
        )
        db.add(new_contract)
        old, new, target_institute = None, value, institute
    else:
        if not current:
            raise ImportConflict(f"{item.change_type} inconsistente: no existe contrato vigente")
        old = {
            "instituto": current.institute_code,
            "cargo": current.role,
            "horasSemanales": float(current.weekly_hours),
            "fechaTermino": current.effective_to.isoformat() if current.effective_to else None,
        }
        declared = item.old_value or {}
        comparisons = {
            "instituto": current.institute_code,
            "cargo": current.role,
            "horasSemanales": Decimal(current.weekly_hours),
            "fechaTermino": current.effective_to.isoformat() if current.effective_to else None,
        }
        for field, actual in comparisons.items():
            if field not in declared:
                continue
            expected = declared[field]
            if field == "horasSemanales":
                expected = Decimal(str(expected))
            if expected != actual:
                raise ImportConflict(f"Delta inconsistente en {field}: el valor anterior no coincide con el estado vigente")
        target_institute = current.institute_code
        current.effective_to = item.effective_date - dt.timedelta(days=1)
        new = item.new_value or {}
        if item.change_type != "BAJA":
            target_institute = str(new.get("instituto", current.institute_code))
            if not db.get(Institute, target_institute):
                db.add(Institute(code=target_institute, name=target_institute))
                db.flush()
            db.add(
                ContractVersion(
                    professional_id=current.professional_id,
                    institute_code=target_institute,
                    role=str(new.get("cargo", current.role)).upper(),
                    area=new.get("area", current.area),
                    weekly_hours=Decimal(str(new.get("horasSemanales", current.weekly_hours))),
                    effective_from=item.effective_date,
                    effective_to=dt.date.fromisoformat(new["fechaTermino"]) if new.get("fechaTermino") else None,
                    source_record_id=item.source_record_id,
                    source_import_id=batch.id,
                )
            )
    audit(
        db,
        principal,
        "contract_delta_applied",
        "contract",
        item.persona_id,
        old_value=old,
        new_value=new,
        justification=item.justification,
        correlation_id=batch.id,
    )
    stored.applied = True
    return item.persona_id, target_institute, item.effective_date.year


def complete_import(db: Session, batch: ImportBatch, expected_rows: int, principal: Principal) -> dict:
    if batch.status == "completed":
        return {"estado": "completed", "reutilizada": True, "importacionId": batch.id}
    if batch.status == "failed":
        raise ImportConflict("La importación falló y no puede completarse")
    if expected_rows != batch.rows_received:
        raise ImportConflict(
            f"Conteo inconsistente: Blue Prism informó {expected_rows}, backend recibió {batch.rows_received}"
        )
    affected: set[tuple[str, str, int]] = set()
    try:
        records = list(
            db.scalars(select(ImportRecord).where(ImportRecord.import_id == batch.id, ImportRecord.applied.is_(False)))
        )
        for stored in records:
            if stored.record_type == "buk":
                affected.add(_apply_buk(db, batch, stored))
            elif stored.record_type == "sic":
                affected.add(_apply_sic(db, batch, stored))
            elif stored.record_type == "delta":
                affected.add(_apply_delta(db, batch, stored, principal))
        db.flush()
        recalculations = []
        if batch.source == ImportSource.BUK.value:
            for person_id, institute, year in sorted(affected):
                recalculations.append(
                    recalculate(db, professional_id=person_id, institute_code=institute, year=year)
                )
        batch.status = "completed"
        batch.completed_at = dt.datetime.now(dt.timezone.utc)
        audit(
            db,
            principal,
            "import_completed",
            "rpa_import",
            batch.id,
            new_value={
                "accepted": batch.rows_accepted,
                "rejected": batch.rows_rejected,
                "affected": len(affected),
            },
            correlation_id=batch.id,
        )
        db.flush()
        return {
            "estado": batch.status,
            "reutilizada": False,
            "importacionId": batch.id,
            "filasAceptadas": batch.rows_accepted,
            "filasRechazadas": batch.rows_rejected,
            "entidadesAfectadas": len(affected),
            "recalculos": recalculations,
        }
    except Exception:
        raise
