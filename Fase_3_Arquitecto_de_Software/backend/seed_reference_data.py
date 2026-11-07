"""Carga al backend los CSV versionados del motor de cálculo.

Uso desde la raíz del repositorio:
  python -m backend.seed_reference_data --instituto Ari:Arica:norte
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, create_local_schema, settings
from .models import AssignmentCatalog, DistributionParameter, Institute, InstitutionalCalendar


DATA_DIR = Path(__file__).parents[1] / "motor-calculo" / "data"
BAND_MAP = {">=40": "T1_>=40", "22-40": "T2_22-39", "<22": "T3_<22"}


@dataclass(frozen=True)
class InstituteSeed:
    code: str
    name: str
    zone: str | None = None


def _rows(filename: str) -> list[dict[str, str]]:
    with (DATA_DIR / filename).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def seed_reference_data(db: Session, institutes: list[InstituteSeed]) -> dict[str, int]:
    group_factors = {row["cod_esp"]: row for row in _rows("factor_grupal.csv")}
    distributions = assignments = calendars = 0

    for raw in _rows("parametros_cargo.csv"):
        role = raw["cargo_homologado"].strip().upper()
        band = BAND_MAP[raw["tramo"]]
        row = db.scalar(
            select(DistributionParameter).where(
                DistributionParameter.role == role,
                DistributionParameter.workload_band == band,
                DistributionParameter.valid_from == dt.date(2026, 1, 1),
            )
        )
        factor = group_factors.get(raw.get("cod_esp", ""))
        if row is None:
            row = DistributionParameter(role=role, workload_band=band, valid_from=dt.date(2026, 1, 1))
            db.add(row)
        row.direct_pct = Decimal(raw["pct_directo"])
        row.indirect_pct = Decimal(raw["pct_indirecto"])
        row.nas_pct = Decimal(raw["pct_nas"])
        row.direct_minutes = int(raw["minutos_directa"])
        row.indirect_minutes = int(raw["minutos_indirecta"])
        row.group_pct = Decimal(factor["pct_grupal"]) if factor else Decimal("0")
        # Valor base para otros IT; Santiago/Concepción se parametriza vía API.
        row.group_size = Decimal(factor["pacientes_otros_it"]) if factor else Decimal("1")
        distributions += 1

    for raw in _rows("asignaciones_especiales.csv"):
        name = raw["nombre"].strip()
        row = db.scalar(select(AssignmentCatalog).where(AssignmentCatalog.name == name))
        if row is None:
            row = AssignmentCatalog(name=name, valid_from=dt.date(2026, 1, 1))
            db.add(row)
        row.weekly_hours = Decimal(raw["horas_semanales"]) if raw["horas_semanales"] else None
        row.requires_dmn = raw["requiere_aprobacion_dmn"].lower() == "true"
        row.active = True
        assignments += 1

    calendar_rows = _rows("calendario_2026.csv")
    for item in institutes:
        institute = db.get(Institute, item.code)
        if institute is None:
            institute = Institute(code=item.code, name=item.name, zone=item.zone)
            db.add(institute)
            db.flush()
        else:
            institute.name, institute.zone = item.name, item.zone
        for raw in calendar_rows:
            month = int(raw["mes"])
            row = db.scalar(
                select(InstitutionalCalendar).where(
                    InstitutionalCalendar.institute_code == item.code,
                    InstitutionalCalendar.year == 2026,
                    InstitutionalCalendar.month == month,
                )
            )
            if row is None:
                row = InstitutionalCalendar(institute_code=item.code, year=2026, month=month)
                db.add(row)
            row.working_days = Decimal(raw["dias_habiles"])
            row.national_holidays = int(raw["inhabiles"])
            row.regional_holidays = 0
            row.special_regime_days = Decimal("0")
            row.zone = item.zone
            calendars += 1

    db.commit()
    return {"distribuciones": distributions, "asignaciones": assignments, "calendarios": calendars}


def _institute(value: str) -> InstituteSeed:
    parts = value.split(":", 2)
    if not parts[0].strip():
        raise argparse.ArgumentTypeError("El código del instituto no puede estar vacío")
    return InstituteSeed(parts[0], parts[1] if len(parts) > 1 else parts[0], parts[2] if len(parts) > 2 else None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga parámetros CSV del motor al backend")
    parser.add_argument(
        "--instituto",
        action="append",
        type=_institute,
        default=[],
        help="CODIGO[:NOMBRE[:ZONA]]. Puede repetirse.",
    )
    args = parser.parse_args()
    if settings.is_sqlite:
        create_local_schema()
    with SessionLocal() as db:
        result = seed_reference_data(db, args.instituto)
    print(result)


if __name__ == "__main__":
    main()
