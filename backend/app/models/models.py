"""SQLAlchemy ORM models mirroring the canonical schema."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# Enum values are plain strings; SQLAlchemy Enum maps to MySQL ENUM.
ROLE = ("RECEPTIONIST", "CASHIER", "ADMIN")
LOCALE = ("en", "ar")
VISIT_TYPE = ("SCHEDULED", "EARLY", "LATE", "WALK_IN")
APPT_STATUS = ("SCHEDULED", "CHECKED_IN", "SERVED", "MISSED", "CANCELLED")
TICKET_STATUS = ("WAITING", "CALLED", "SERVING", "NO_SHOW", "DONE", "CANCELLED")
IMPORT_STATUS = ("RUNNING", "SUCCEEDED", "FAILED", "PARTIAL")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(Enum(*ROLE))
    preferred_locale: Mapped[str] = mapped_column(Enum(*LOCALE), default="en")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))


class Cashier(Base):
    __tablename__ = "cashiers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))


class Guardian(Base):
    __tablename__ = "guardians"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_guardian_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_student_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"))
    name: Mapped[str] = mapped_column(String(200))


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(60))
    external_appointment_id: Mapped[str] = mapped_column(String(120))
    booking_number: Mapped[str] = mapped_column(String(100))
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"))
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"))
    scheduled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    status: Mapped[str] = mapped_column(Enum(*APPT_STATUS), default="SCHEDULED")
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    source_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=False))
    source_payload: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (UniqueConstraint("source_system", "external_appointment_id", name="uq_appointment_source"),)


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_date: Mapped[dt.date] = mapped_column(Date)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"))
    visit_type: Mapped[str] = mapped_column(Enum(*VISIT_TYPE))
    multi_appointment: Mapped[bool] = mapped_column(Boolean, default=False)
    arrival_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    queue_entered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(500))


class VisitAppointment(Base):
    __tablename__ = "visit_appointments"
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), primary_key=True)
    __table_args__ = (UniqueConstraint("appointment_id", name="uq_active_appointment_visit"),)


class DailyCounter(Base):
    __tablename__ = "daily_counters"
    service_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    last_ticket_number: Mapped[int] = mapped_column(Integer)


class QueueTicket(Base):
    __tablename__ = "queue_tickets"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), unique=True)
    service_date: Mapped[dt.date] = mapped_column(Date)
    ticket_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Enum(*TICKET_STATUS))
    cashier_id: Mapped[int | None] = mapped_column(ForeignKey("cashiers.id"))
    called_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=False))
    service_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=False))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=False))
    recall_count: Mapped[int] = mapped_column(Integer, default=0)
    cancellation_reason: Mapped[str | None] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (UniqueConstraint("service_date", "ticket_number", name="uq_daily_ticket"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    idempotency_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    operation: Mapped[str] = mapped_column(String(60))
    response_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[int] = mapped_column(Integer)
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str | None] = mapped_column(String(30))
    details: Mapped[dict | None] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(100))


class ImportRun(Base):
    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_date: Mapped[dt.date] = mapped_column(Date)
    source_system: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=False))
    status: Mapped[str] = mapped_column(Enum(*IMPORT_STATUS))
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    setting_value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=False))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
