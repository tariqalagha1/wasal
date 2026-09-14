"""Daily appointment import service.

Copies the service day's bookings into the QMS operational database.
Idempotent by ``(source_system, external_appointment_id)``. Re-running must not
duplicate appointments, guardians, or students. Operational history is never
reverted: an already CHECKED_IN/SERVED appointment keeps its status.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import errors
from app.core.time import local_date_of, now_utc

APPT_KEYS = (
    "external_appointment_id",
    "booking_number",
    "guardian_name",
    "student_name",
    "scheduled_at",
)


async def _upsert_guardian(conn: AsyncConnection, external_id: str | None, name: str, phone: str | None) -> int:
    if external_id:
        await conn.execute(
            text(
                "INSERT INTO guardians (external_guardian_id, name, phone) VALUES (:e, :n, :p) AS new "
                "ON DUPLICATE KEY UPDATE name = new.name, phone = COALESCE(new.phone, guardians.phone)"
            ),
            {"e": external_id, "n": name, "p": phone},
        )
        row = await conn.execute(
            text("SELECT id FROM guardians WHERE external_guardian_id = :e"), {"e": external_id}
        )
        return row.scalar_one()
    row = await conn.execute(text("SELECT id FROM guardians WHERE name = :n ORDER BY id LIMIT 1"), {"n": name})
    existing = row.first()
    if existing is not None:
        return existing.id
    return (
        await conn.execute(
            text("INSERT INTO guardians (external_guardian_id, name, phone) VALUES (NULL, :n, :p)"),
            {"n": name, "p": phone},
        )
    ).lastrowid


async def _upsert_student(conn: AsyncConnection, external_id: str | None, name: str | None, guardian_id: int) -> int | None:
    if not name:
        return None
    if external_id:
        await conn.execute(
            text(
                "INSERT INTO students (external_student_id, guardian_id, name) VALUES (:e, :g, :n) AS new "
                "ON DUPLICATE KEY UPDATE guardian_id = new.guardian_id, name = new.name"
            ),
            {"e": external_id, "g": guardian_id, "n": name},
        )
        row = await conn.execute(
            text("SELECT id FROM students WHERE external_student_id = :e"), {"e": external_id}
        )
        return row.scalar_one()
    return (
        await conn.execute(
            text("INSERT INTO students (external_student_id, guardian_id, name) VALUES (NULL, :g, :n)"),
            {"g": guardian_id, "n": name},
        )
    ).lastrowid


async def _upsert_appointment(conn: AsyncConnection, rec: dict, guardian_id: int, student_id: int | None, service_date) -> str:
    """Upsert one appointment; returns 'inserted', 'updated', or 'unchanged'."""
    cancelled = bool(rec.get("cancelled", False))
    status = "CANCELLED" if cancelled else "SCHEDULED"
    scheduled_at = rec["scheduled_at"]
    if isinstance(scheduled_at, str):
        scheduled_at = dt.datetime.fromisoformat(scheduled_at)
    source_updated_at = rec.get("source_updated_at")
    if isinstance(source_updated_at, str):
        source_updated_at = dt.datetime.fromisoformat(source_updated_at)
    payload = rec.get("source_payload")
    payload_json = json.dumps(payload) if payload is not None else None

    existing = (
        await conn.execute(
            text("SELECT id, status FROM appointments WHERE source_system = :ss AND external_appointment_id = :eaid"),
            {"ss": rec["source_system"], "eaid": rec["external_appointment_id"]},
        )
    ).first()

    if existing is None:
        await conn.execute(
            text(
                "INSERT INTO appointments (source_system, external_appointment_id, booking_number, guardian_id, "
                "student_id, scheduled_at, status, imported_at, source_updated_at, source_payload) "
                "VALUES (:ss, :eaid, :bn, :gid, :sid, :sat, :status, :now, :suat, :payload)"
            ),
            {
                "ss": rec["source_system"],
                "eaid": rec["external_appointment_id"],
                "bn": rec["booking_number"],
                "gid": guardian_id,
                "sid": student_id,
                "sat": scheduled_at,
                "status": status,
                "now": now_utc(),
                "suat": source_updated_at,
                "payload": payload_json,
            },
        )
        return "inserted"

    # Update safety: never revert operational status or erase history.
    if existing.status == "SCHEDULED":
        new_status = "CANCELLED" if cancelled else "SCHEDULED"
        await conn.execute(
            text(
                "UPDATE appointments SET booking_number = :bn, guardian_id = :gid, student_id = :sid, "
                "scheduled_at = :sat, status = :status, source_updated_at = :suat, source_payload = :payload "
                "WHERE source_system = :ss AND external_appointment_id = :eaid"
            ),
            {
                "bn": rec["booking_number"],
                "gid": guardian_id,
                "sid": student_id,
                "sat": scheduled_at,
                "status": new_status,
                "suat": source_updated_at,
                "payload": payload_json,
                "ss": rec["source_system"],
                "eaid": rec["external_appointment_id"],
            },
        )
        return "updated"
    else:
        await conn.execute(
            text(
                "UPDATE appointments SET source_updated_at = :suat, source_payload = :payload "
                "WHERE source_system = :ss AND external_appointment_id = :eaid"
            ),
            {"suat": source_updated_at, "payload": payload_json, "ss": rec["source_system"], "eaid": rec["external_appointment_id"]},
        )
        return "unchanged"


async def import_records(
    *,
    service_date,
    source_system: str,
    records: list[dict],
    actor_user_id: int | None = None,
) -> dict:
    """Import a list of source booking records idempotently."""
    async with _engine_ctx() as conn:
        async with conn.begin():
            started = now_utc()
            inserted = updated = rejected = unchanged = 0
            errors_list: list[str] = []

            for rec in records:
                rec = dict(rec)
                rec["source_system"] = source_system
                # Validate required fields.
                missing = [k for k in APPT_KEYS if not rec.get(k)]
                if missing:
                    rejected += 1
                    errors_list.append(f"{rec.get('external_appointment_id')}: missing {missing}")
                    continue
                try:
                    guardian_id = await _upsert_guardian(
                        conn, rec.get("guardian_external_id"), rec["guardian_name"], rec.get("guardian_phone")
                    )
                    student_id = await _upsert_student(
                        conn, rec.get("student_external_id"), rec.get("student_name"), guardian_id
                    )
                    outcome = await _upsert_appointment(conn, rec, guardian_id, student_id, service_date)
                    if outcome == "inserted":
                        inserted += 1
                    elif outcome == "updated":
                        updated += 1
                    else:
                        unchanged += 1
                except Exception as exc:  # per-row isolation
                    rejected += 1
                    errors_list.append(f"{rec.get('external_appointment_id')}: {type(exc).__name__} {exc}")

            status = "SUCCEEDED"
            if rejected and (inserted or updated):
                status = "PARTIAL"
            elif rejected:
                status = "FAILED"

            run_id = (
                await conn.execute(
                    text(
                        "INSERT INTO import_runs (service_date, source_system, started_at, completed_at, status, "
                        "read_count, inserted_count, updated_count, rejected_count, error_summary) "
                        "VALUES (:d, :ss, :started, :completed, :status, :read, :ins, :upd, :rej, :err)"
                    ),
                    {
                        "d": service_date,
                        "ss": source_system,
                        "started": started,
                        "completed": now_utc(),
                        "status": status,
                        "read": len(records),
                        "ins": inserted,
                        "upd": updated,
                        "rej": rejected,
                        "err": "\n".join(errors_list) if errors_list else None,
                    },
                )
            ).lastrowid

            return {
                "run_id": run_id,
                "status": status,
                "read": len(records),
                "inserted": inserted,
                "updated": updated,
                "unchanged": unchanged,
                "rejected": rejected,
                "errors": errors_list,
            }


def _engine_ctx():
    from app.core.db import engine

    return engine.connect()


def demo_records(service_date, count: int = 24) -> list[dict]:
    """Deterministic demo booking source for development and acceptance runs."""
    base = dt.datetime.combine(service_date, dt.time(8, 0, 0))
    records = []
    # A small set of guardians, several with multiple students (multi-appointment).
    guardians = [
        ("G-001", "Abdullah Al-Otaibi", "0500000001"),
        ("G-002", "Khalid Al-Harbi", "0500000002"),
        ("G-003", "Sara Al-Qahtani", "0500000003"),
        ("G-004", "Fatimah Al-Shammari", "0500000004"),
        ("G-005", "Mansour Al-Dossari", "0500000005"),
        ("G-006", "Noura Al-Ghamdi", "0500000006"),
        ("G-007", "Omar Al-Zahrani", "0500000007"),
        ("G-008", "Layla Al-Anazi", "0500000008"),
    ]
    for i in range(count):
        g = guardians[i % len(guardians)]
        student_n = (i % 3) + 1
        slot_minutes = 9 * (i + 1)  # spread through the morning
        scheduled = base + dt.timedelta(minutes=slot_minutes)
        records.append(
            {
                "external_appointment_id": f"APP-{i + 1:03d}",
                "booking_number": f"BKG-{1000 + i}",
                "guardian_external_id": g[0],
                "guardian_name": g[1],
                "guardian_phone": g[2],
                "student_external_id": f"{g[0]}-S{student_n}",
                "student_name": f"Student {student_n} ({g[1]})",
                "scheduled_at": scheduled,
                "source_updated_at": scheduled,
                "cancelled": False,
                "source_payload": {"demo": True, "seq": i},
            }
        )
    return records
