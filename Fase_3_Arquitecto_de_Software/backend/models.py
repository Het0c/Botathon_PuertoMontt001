from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def uid() -> str:
    return str(uuid.uuid4())


class Institute(Base):
    __tablename__ = "institutes"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    zone: Mapped[str | None] = mapped_column(String(80))


class Professional(Base):
    __tablename__ = "professionals"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))


class ImportBatch(Base):
    __tablename__ = "rpa_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="created")
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRecord(Base):
    __tablename__ = "rpa_import_records"
    __table_args__ = (UniqueConstraint("import_id", "source_record_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    import_id: Mapped[str] = mapped_column(ForeignKey("rpa_imports.id", ondelete="CASCADE"), index=True)
    source_record_id: Mapped[str] = mapped_column(String(160))
    record_type: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportValidationError(Base):
    __tablename__ = "rpa_import_errors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    import_id: Mapped[str] = mapped_column(ForeignKey("rpa_imports.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int | None] = mapped_column(Integer)
    field: Mapped[str | None] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)


class ContractVersion(Base):
    __tablename__ = "contract_versions"
    __table_args__ = (
        CheckConstraint("weekly_hours >= 0 AND weekly_hours <= 60"),
        UniqueConstraint("professional_id", "institute_code", "effective_from", "source_record_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    professional_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"), index=True)
    role: Mapped[str] = mapped_column(String(160))
    area: Mapped[str | None] = mapped_column(String(120))
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    effective_from: Mapped[dt.date] = mapped_column(Date)
    effective_to: Mapped[dt.date | None] = mapped_column(Date)
    source_record_id: Mapped[str] = mapped_column(String(160))
    source_import_id: Mapped[str | None] = mapped_column(ForeignKey("rpa_imports.id"))


class Unavailability(Base):
    __tablename__ = "unavailability_periods"
    __table_args__ = (CheckConstraint("days >= 0"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    professional_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    days: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    source_import_id: Mapped[str | None] = mapped_column(ForeignKey("rpa_imports.id"))


class DistributionParameter(Base):
    __tablename__ = "distribution_parameters"
    __table_args__ = (
        CheckConstraint("direct_pct >= 0 AND indirect_pct >= 0 AND nas_pct >= 0"),
        CheckConstraint("direct_pct + indirect_pct + nas_pct <= 1.000001"),
        UniqueConstraint("role", "workload_band", "valid_from"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    role: Mapped[str] = mapped_column(String(160), index=True)
    workload_band: Mapped[str] = mapped_column(String(20), index=True)
    direct_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    indirect_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    nas_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    direct_minutes: Mapped[int] = mapped_column(Integer)
    indirect_minutes: Mapped[int] = mapped_column(Integer, default=30)
    group_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    group_size: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("1"))
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)


class SystemParameter(Base):
    __tablename__ = "system_parameters"
    __table_args__ = (UniqueConstraint("code", "valid_from"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(String(255))
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)


class LegalWorkweekReference(Base):
    __tablename__ = "legal_workweek_references"
    __table_args__ = (UniqueConstraint("valid_from"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255))


class InstitutionalCalendar(Base):
    __tablename__ = "institutional_calendars"
    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12"),
        CheckConstraint("working_days >= 0 AND working_days <= 31"),
        UniqueConstraint("institute_code", "year", "month"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    working_days: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    national_holidays: Mapped[int] = mapped_column(Integer, default=0)
    regional_holidays: Mapped[int] = mapped_column(Integer, default=0)
    special_regime_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"))
    zone: Mapped[str | None] = mapped_column(String(80))


class AssignmentCatalog(Base):
    __tablename__ = "assignment_catalog"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    weekly_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_dmn: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[dt.date] = mapped_column(Date)


class AssignmentRequest(Base):
    __tablename__ = "assignment_requests"
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected','cancelled')"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    professional_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"))
    catalog_id: Mapped[str] = mapped_column(ForeignKey("assignment_catalog.id"))
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_by: Mapped[str] = mapped_column(String(120))
    decided_by: Mapped[str | None] = mapped_column(String(120))
    requested_reason: Mapped[str] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Replacement(Base):
    __tablename__ = "replacements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    holder_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    replacement_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"))
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active")


class Vacancy(Base):
    __tablename__ = "vacancies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"), index=True)
    role: Mapped[str] = mapped_column(String(160))
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="open")
    include_in_planning: Mapped[bool] = mapped_column(Boolean, default=True)


class MonthlyPlanning(Base):
    __tablename__ = "monthly_planning"
    __table_args__ = (UniqueConstraint("professional_id", "institute_code", "year", "month"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    professional_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"), index=True)
    role: Mapped[str] = mapped_column(String(160), index=True)
    area: Mapped[str | None] = mapped_column(String(120), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    workload_band: Mapped[str] = mapped_column(String(20))
    contracted_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    direct_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    indirect_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    nas_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    absence_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    planned_direct: Mapped[int] = mapped_column(Integer)
    planned_indirect: Mapped[int] = mapped_column(Integer)
    planned_total: Mapped[int] = mapped_column(Integer)
    target_total: Mapped[int] = mapped_column(Integer)
    foja: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    parameters_version: Mapped[str] = mapped_column(String(120))
    calculated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))


class SicActual(Base):
    __tablename__ = "sic_actuals"
    __table_args__ = (UniqueConstraint("professional_id", "institute_code", "year", "month"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    professional_id: Mapped[str] = mapped_column(ForeignKey("professionals.id"), index=True)
    institute_code: Mapped[str] = mapped_column(ForeignKey("institutes.code"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    executed_direct: Mapped[int] = mapped_column(Integer)
    executed_indirect: Mapped[int] = mapped_column(Integer)
    validated_report: Mapped[bool] = mapped_column(Boolean, default=True)
    source_import_id: Mapped[str | None] = mapped_column(ForeignKey("rpa_imports.id"))


class AuditEvent(Base):
    __tablename__ = "plan_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str | None] = mapped_column("actor_id", String(36), nullable=True)
    actor_id: Mapped[str] = mapped_column("actor_text", String(120))
    actor_role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column("operation", String(80))
    revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(120))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    justification: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(30))
    correlation_id: Mapped[str | None] = mapped_column(String(120), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[dt.datetime] = mapped_column("created_at", DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), index=True)
