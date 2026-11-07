import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import DistributionParameter, InstitutionalCalendar, Institute
from backend.schemas import Principal, Role


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def rpa() -> Principal:
    return Principal(actorId="blue-prism", role=Role.RPA, origin="blue_prism")


@pytest.fixture()
def rrhh() -> Principal:
    return Principal(actorId="rrhh-test", role=Role.RRHH, origin="user")


@pytest.fixture()
def dmn() -> Principal:
    return Principal(actorId="dmn-test", role=Role.DMN, origin="user")


@pytest.fixture()
def configured_db(db: Session) -> Session:
    db.add(Institute(code="Ari", name="Instituto Arica", zone="norte"))
    for month in range(1, 13):
        db.add(
            InstitutionalCalendar(
                institute_code="Ari",
                year=2026,
                month=month,
                working_days=Decimal("21"),
                regional_holidays=1 if month == 6 else 0,
                zone="norte",
            )
        )
    for band in ("T1_>=40", "T2_22-39", "T3_<22"):
        db.add(
            DistributionParameter(
                role="MEDICO FISIATRA",
                workload_band=band,
                direct_pct=Decimal("0.65"),
                indirect_pct=Decimal("0.15"),
                nas_pct=Decimal("0.20"),
                direct_minutes=40,
                indirect_minutes=30,
                valid_from=dt.date(2026, 1, 1),
            )
        )
    db.commit()
    return db
