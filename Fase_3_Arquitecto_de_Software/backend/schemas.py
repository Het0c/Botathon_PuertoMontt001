from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from pydantic.alias_generators import to_camel


NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class Role(StrEnum):
    RPA = "rpa"
    RRHH = "rrhh"
    PROFESSIONAL = "professional"
    MANAGEMENT = "management"
    DMN = "dmn"


class ImportSource(StrEnum):
    BUK = "BUK"
    SIC = "SIC"


class ImportCreate(CamelModel):
    source: ImportSource
    filename: NonEmpty
    file_hash: Annotated[str, StringConstraints(min_length=16, max_length=128)]
    idempotency_key: Annotated[str, StringConstraints(min_length=8, max_length=120)]


class ContractPayload(CamelModel):
    effective_from: dt.date = Field(alias="fechaInicio")
    effective_to: dt.date | None = Field(default=None, alias="fechaTermino")
    weekly_hours: Decimal = Field(alias="horasSemanales", ge=0, le=60)

    @model_validator(mode="after")
    def valid_dates(self) -> "ContractPayload":
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("fechaTermino no puede ser anterior a fechaInicio")
        return self


class MonthAbsence(CamelModel):
    sick_leave_days: Decimal = Field(default=Decimal("0"), alias="licencias", ge=0, le=31)
    vacation_days: Decimal = Field(default=Decimal("0"), alias="vacaciones", ge=0, le=31)

    @property
    def total_days(self) -> Decimal:
        return self.sick_leave_days + self.vacation_days


class BukRecord(CamelModel):
    source_record_id: NonEmpty
    persona_id: NonEmpty = Field(alias="personaId")
    instituto: NonEmpty
    institute_name: str | None = Field(default=None, alias="nombreInstituto", max_length=160)
    cargo: NonEmpty
    area: str | None = Field(default=None, max_length=120)
    reg_sic: Literal["D - SIC"] = Field(default="D - SIC", alias="regSic")
    planning_year: int = Field(default=2026, alias="anioPlanificacion", ge=2020, le=2100)
    contrato: ContractPayload
    meses: dict[str, MonthAbsence] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_motor_contract(cls, value: object) -> object:
        """Acepta también el contrato JSON ya definido por motor-calculo/data.

        Blue Prism sigue siendo responsable de filtrar Reg_SIC antes de exportar.
        El Literal de ``regSic`` mantiene una segunda barrera en el backend.
        """
        if not isinstance(value, dict) or "contrato" in value:
            return value

        raw = dict(value)
        person_id = raw.get("personaId")
        if person_id is not None:
            raw["personaId"] = str(person_id)
        planning_year = int(raw.get("anioPlanificacion", 2026))
        monthly_hours = raw.get("horasSemanalesPorMes") or []
        if len(monthly_hours) != 12:
            return value

        first_hours = next((hours for hours in monthly_hours if Decimal(str(hours)) > 0), 0)
        raw.setdefault("sourceRecordId", f"BUK-{person_id}-{planning_year}")
        raw.setdefault("regSic", "D - SIC")
        raw.setdefault("anioPlanificacion", planning_year)
        raw.setdefault("area", raw.get("codEsp"))
        raw["contrato"] = {
            "fechaInicio": raw.get("fechaIngreso"),
            "fechaTermino": raw.get("fechaTermino"),
            "horasSemanales": first_hours,
        }

        discounts = raw.get("descuentos") or {}
        vacation = discounts.get("vacacionesSemanas") or [0] * 12
        sick_leave = discounts.get("licenciasSemanas") or [0] * 12
        permissions = discounts.get("permisosSemanas") or [0] * 12
        if all(len(items) == 12 for items in (vacation, sick_leave, permissions)):
            # La API operacional almacena días; el contrato histórico expresa semanas.
            raw["meses"] = {
                f"{month:02d}": {
                    "vacaciones": Decimal(str(vacation[month - 1])) * Decimal("5"),
                    "licencias": (
                        Decimal(str(sick_leave[month - 1])) + Decimal(str(permissions[month - 1]))
                    )
                    * Decimal("5"),
                }
                for month in range(1, 13)
                if vacation[month - 1] or sick_leave[month - 1] or permissions[month - 1]
            }
        return raw

    @field_validator("meses")
    @classmethod
    def valid_months(cls, value: dict[str, MonthAbsence]) -> dict[str, MonthAbsence]:
        if any(key not in {f"{month:02d}" for month in range(1, 13)} for key in value):
            raise ValueError("meses solo admite claves 01 a 12")
        return value


class SicRecord(CamelModel):
    source_record_id: NonEmpty
    persona_id: NonEmpty = Field(alias="personaId")
    instituto: NonEmpty
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    executed_direct: int = Field(alias="atencionesDirectas", ge=0)
    executed_indirect: int = Field(default=0, alias="atencionesIndirectas", ge=0)
    validated_report: bool = Field(default=True, alias="reporteValidado")


class RecordsEnvelope(CamelModel):
    records: list[dict] = Field(min_length=1, max_length=5000)


class ContractDelta(CamelModel):
    source_record_id: NonEmpty
    persona_id: NonEmpty = Field(alias="personaId")
    change_type: Literal[
        "ALTA", "BAJA", "CAMBIO_CARGO", "CAMBIO_HORAS", "CAMBIO_INSTITUTO", "CAMBIO_BENEFICIO", "CAMBIO_VIGENCIA"
    ] = Field(alias="tipoCambio")
    effective_date: dt.date = Field(alias="fechaEfectiva")
    old_value: dict | None = Field(default=None, alias="valorAnterior")
    new_value: dict | None = Field(default=None, alias="valorNuevo")
    justification: NonEmpty = Field(alias="justificacion")


class DeltasEnvelope(CamelModel):
    deltas: list[ContractDelta] = Field(min_length=1, max_length=5000)


class ValidationErrorInput(CamelModel):
    row_number: int | None = Field(default=None, alias="fila", ge=1)
    field: str | None = Field(default=None, alias="campo", max_length=120)
    code: NonEmpty = Field(alias="codigo")
    message: NonEmpty = Field(alias="mensaje")


class ValidationErrorsEnvelope(CamelModel):
    errors: list[ValidationErrorInput] = Field(min_length=1, max_length=5000)


class CompleteImport(CamelModel):
    expected_rows: int = Field(alias="filasEsperadas", ge=0)


class DistributionInput(CamelModel):
    role: NonEmpty = Field(alias="cargo")
    workload_band: Literal["T1_>=40", "T2_22-39", "T3_<22"] = Field(alias="tramo")
    direct_pct: Decimal = Field(alias="pctDirecto", ge=0, le=1)
    indirect_pct: Decimal = Field(alias="pctIndirecto", ge=0, le=1)
    nas_pct: Decimal = Field(alias="pctNas", ge=0, le=1)
    direct_minutes: Literal[30, 40, 45, 60] = Field(alias="minutosDirecta")
    indirect_minutes: int = Field(default=30, alias="minutosIndirecta", ge=1, le=240)
    group_pct: Decimal = Field(default=Decimal("0"), alias="pctGrupal", ge=0, le=1)
    group_size: Decimal = Field(default=Decimal("1"), alias="pacientesGrupo", ge=1, le=100)
    valid_from: dt.date = Field(alias="vigenteDesde")
    valid_to: dt.date | None = Field(default=None, alias="vigenteHasta")

    @model_validator(mode="after")
    def percentages_sum(self) -> "DistributionInput":
        if self.direct_pct + self.indirect_pct + self.nas_pct > Decimal("1"):
            raise ValueError("los porcentajes directo, indirecto y NAS no pueden superar 100%")
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("vigenteHasta no puede ser anterior a vigenteDesde")
        return self


class CalendarInput(CamelModel):
    instituto: NonEmpty
    institute_name: str | None = Field(default=None, alias="nombreInstituto", max_length=160)
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    working_days: Decimal = Field(alias="diasHabiles", ge=0, le=31)
    national_holidays: int = Field(default=0, alias="feriadosNacionales", ge=0, le=31)
    regional_holidays: int = Field(default=0, alias="feriadosRegionales", ge=0, le=31)
    special_regime_days: Decimal = Field(default=Decimal("0"), alias="diasRegimenEspecial", ge=0, le=31)
    zone: str | None = Field(default=None, alias="zona", max_length=80)


class TargetParameterInput(CamelModel):
    value: Decimal = Field(alias="valor", ge=0, le=1)
    valid_from: dt.date = Field(alias="vigenteDesde")
    valid_to: dt.date | None = Field(default=None, alias="vigenteHasta")
    justification: NonEmpty = Field(alias="justificacion")


class LegalReferenceInput(CamelModel):
    weekly_hours: Decimal = Field(alias="horasSemanales", gt=0, le=60)
    valid_from: dt.date = Field(alias="vigenteDesde")
    valid_to: dt.date | None = Field(default=None, alias="vigenteHasta")
    description: NonEmpty = Field(alias="descripcion")


class AssignmentCatalogInput(CamelModel):
    name: NonEmpty = Field(alias="nombre")
    weekly_hours: Decimal | None = Field(default=None, alias="horasSemanales", gt=0, le=40)
    active: bool = Field(default=True, alias="activa")
    requires_dmn: bool = Field(default=False, alias="requiereDmn")
    valid_from: dt.date = Field(alias="vigenteDesde")


class AssignmentRequestInput(CamelModel):
    professional_id: NonEmpty = Field(alias="personaId")
    institute_code: NonEmpty = Field(alias="instituto")
    catalog_id: NonEmpty = Field(alias="asignacionId")
    valid_from: dt.date = Field(alias="vigenteDesde")
    valid_to: dt.date | None = Field(default=None, alias="vigenteHasta")
    reason: NonEmpty = Field(alias="justificacion")

    @model_validator(mode="after")
    def dates(self) -> "AssignmentRequestInput":
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("vigenteHasta no puede ser anterior a vigenteDesde")
        return self


class AssignmentDecision(CamelModel):
    reason: NonEmpty = Field(alias="justificacion")


class RecalculateRequest(CamelModel):
    professional_id: str | None = Field(default=None, alias="personaId", max_length=80)
    institute_code: str | None = Field(default=None, alias="instituto", max_length=20)
    year: int = Field(default=2026, ge=2020, le=2100)
    from_month: int = Field(default=1, alias="mesDesde", ge=1, le=12)


class SimulationInput(CamelModel):
    professional_id: NonEmpty = Field(alias="personaId")
    institute_code: NonEmpty = Field(alias="instituto")
    year: int = Field(default=2026, ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    target_pct: Decimal | None = Field(default=None, alias="pctMeta", ge=0, le=1)
    direct_pct: Decimal | None = Field(default=None, alias="pctDirecto", ge=0, le=1)
    indirect_pct: Decimal | None = Field(default=None, alias="pctIndirecto", ge=0, le=1)
    direct_minutes: Literal[30, 40, 45, 60] | None = Field(default=None, alias="minutosDirecta")


class Principal(CamelModel):
    actor_id: str
    role: Role
    origin: Literal["blue_prism", "user", "backend"]
