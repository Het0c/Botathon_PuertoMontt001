from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import rpa_principal
from ..database import get_db
from ..models import ContractVersion, ImportBatch, ImportValidationError
from ..schemas import (
    CompleteImport,
    DeltasEnvelope,
    ImportCreate,
    Principal,
    RecordsEnvelope,
    ValidationErrorsEnvelope,
)
from ..services.imports import (
    ImportConflict,
    add_external_errors,
    complete_import,
    create_import,
    stage_deltas,
    stage_records,
)


router = APIRouter(prefix="/api/v1/rpa", tags=["Blue Prism / RPA"])


def get_batch(import_id: str, db: Session) -> ImportBatch:
    batch = db.get(ImportBatch, import_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Importación no encontrada")
    return batch


def status_dict(batch: ImportBatch, db: Session) -> dict:
    errors = list(
        db.scalars(
            select(ImportValidationError)
            .where(ImportValidationError.import_id == batch.id)
            .order_by(ImportValidationError.row_number)
            .limit(100)
        )
    )
    return {
        "importacionId": batch.id,
        "origen": batch.source,
        "archivo": batch.filename,
        "estado": batch.status,
        "filasRecibidas": batch.rows_received,
        "filasAceptadas": batch.rows_accepted,
        "filasRechazadas": batch.rows_rejected,
        "creadaEn": batch.created_at,
        "completadaEn": batch.completed_at,
        "errores": [
            {
                "fila": item.row_number,
                "campo": item.field,
                "codigo": item.code,
                "mensaje": item.message,
            }
            for item in errors
        ],
    }


@router.get("/contracts/snapshot")
def contracts_snapshot(
    principal: Principal = Depends(rpa_principal), db: Session = Depends(get_db)
) -> dict:
    rows = list(
        db.scalars(
            select(ContractVersion).where(
                or_(ContractVersion.effective_to.is_(None), ContractVersion.effective_to >= __import__("datetime").date.today())
            )
        )
    )
    return {
        "generadoPara": principal.actor_id,
        "contratos": [
            {
                "personaId": row.professional_id,
                "instituto": row.institute_code,
                "cargo": row.role,
                "area": row.area,
                "horasSemanales": float(row.weekly_hours),
                "fechaInicio": row.effective_from,
                "fechaTermino": row.effective_to,
            }
            for row in rows
        ],
    }


@router.post("/imports", status_code=status.HTTP_201_CREATED)
def imports_create(
    payload: ImportCreate,
    response: Response,
    principal: Principal = Depends(rpa_principal),
    db: Session = Depends(get_db),
) -> dict:
    try:
        batch, created = create_import(db, payload, principal)
        db.commit()
    except ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return {"importacionId": batch.id, "estado": batch.status, "reutilizada": not created}


@router.post("/imports/{import_id}/records")
def imports_records(
    import_id: str,
    payload: RecordsEnvelope,
    principal: Principal = Depends(rpa_principal),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    try:
        result = stage_records(db, get_batch(import_id, db), payload.records)
        db.commit()
        return result
    except ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/imports/{import_id}/deltas")
def imports_deltas(
    import_id: str,
    payload: DeltasEnvelope,
    principal: Principal = Depends(rpa_principal),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    try:
        result = stage_deltas(db, get_batch(import_id, db), payload.deltas)
        db.commit()
        return result
    except ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/imports/{import_id}/validation-errors")
def imports_validation_errors(
    import_id: str,
    payload: ValidationErrorsEnvelope,
    principal: Principal = Depends(rpa_principal),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    try:
        result = add_external_errors(db, get_batch(import_id, db), payload.errors)
        db.commit()
        return result
    except ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/imports/{import_id}/complete")
def imports_complete(
    import_id: str,
    payload: CompleteImport,
    principal: Principal = Depends(rpa_principal),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = complete_import(db, get_batch(import_id, db), payload.expected_rows, principal)
        db.commit()
        return result
    except ImportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        failed = db.get(ImportBatch, import_id)
        if failed and failed.status != "completed":
            failed.status = "failed"
            db.commit()
        raise


@router.get("/imports/{import_id}/status")
def imports_status(
    import_id: str,
    principal: Principal = Depends(rpa_principal),
    db: Session = Depends(get_db),
) -> dict:
    del principal
    return status_dict(get_batch(import_id, db), db)
