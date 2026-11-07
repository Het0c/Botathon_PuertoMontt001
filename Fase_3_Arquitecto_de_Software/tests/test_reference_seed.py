from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AssignmentCatalog, DistributionParameter, InstitutionalCalendar
from backend.seed_reference_data import InstituteSeed, seed_reference_data


def test_versioned_motor_csvs_seed_backend_tables(db: Session) -> None:
    result = seed_reference_data(db, [InstituteSeed("Ari", "Arica", "norte")])

    assert result["distribuciones"] > 200
    assert result["asignaciones"] >= 30
    assert result["calendarios"] == 12
    assert db.scalar(select(func.count()).select_from(InstitutionalCalendar)) == 12
    assert db.scalar(select(func.count()).select_from(DistributionParameter)) == result["distribuciones"]
    assert db.scalar(
        select(func.count()).select_from(AssignmentCatalog).where(AssignmentCatalog.weekly_hours.is_(None))
    ) > 0
