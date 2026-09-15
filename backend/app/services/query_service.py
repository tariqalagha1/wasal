"""Read-only query service (authoritative state reconstruction).

All reads hit MySQL directly. Public display/calling-screen queries expose no
guardian, student, phone, booking, or appointment details.
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.db import engine
from app.core.time import today_local


async def _conn():
    return engine.connect()


async def today_appointments(service_date=None, search: str | None = None) -> list[dict]:
    service_date = service_date or today_local()
    where = "DATE(a.scheduled_at) = :d"
    params: dict = {"d": service_date}
    if search:
        where += " AND (a.booking_number LIKE :s OR g.name LIKE :s OR g.external_guardian_id LIKE :s OR g.phone LIKE :s)"
        params["s"] = f"%{search}%"
    sql = f"""
        SELECT a.id, a.booking_number, a.external_appointment_id, a.scheduled_at, a.status,
               g.id AS guardian_id, g.name AS guardian_name, g.external_guardian_id, g.phone,
               s.name AS student_name
        FROM appointments a
        JOIN guardians g ON g.id = a.guardian_id
        LEFT JOIN students s ON s.id = a.student_id
        WHERE {where}
        ORDER BY a.scheduled_at ASC, a.id ASC
    """
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params)).fetchall()
    return [_row(r) for r in rows]


async def guardian_appointments_today(guardian_id: int, service_date=None) -> list[dict]:
    service_date = service_date or today_local()
    sql = """
        SELECT a.id, a.booking_number, a.external_appointment_id, a.scheduled_at, a.status,
               g.id AS guardian_id, g.name AS guardian_name, g.external_guardian_id, g.phone,
               s.name AS student_name
        FROM appointments a
        JOIN guardians g ON g.id = a.guardian_id
        LEFT JOIN students s ON s.id = a.student_id
        WHERE a.guardian_id = :gid AND DATE(a.scheduled_at) = :d
        ORDER BY a.scheduled_at ASC, a.id ASC
    """
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), {"gid": guardian_id, "d": service_date})).fetchall()
    return [_row(r) for r in rows]


async def waiting_queue(service_date=None) -> list[dict]:
    service_date = service_date or today_local()
    sql = """
        SELECT t.id, t.ticket_number, t.status, t.cashier_id, t.called_at, t.version,
               v.id AS visit_id, v.visit_type, v.multi_appointment, v.queue_entered_at,
               g.name AS guardian_name
        FROM queue_tickets t
        JOIN visits v ON v.id = t.visit_id
        JOIN guardians g ON g.id = v.guardian_id
        WHERE t.service_date = :d AND t.status = 'WAITING'
        ORDER BY v.queue_entered_at ASC, t.ticket_number ASC
    """
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), {"d": service_date})).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "ticket_number": r.ticket_number,
                "status": r.status,
                "visit_type": r.visit_type,
                "multi_appointment": bool(r.multi_appointment),
                "queue_entered_at": r.queue_entered_at.isoformat(sep=" ") if r.queue_entered_at else None,
                "version": r.version,
            }
        )
    return out


async def cashiers_state(service_date=None) -> list[dict]:
    service_date = service_date or today_local()
    sql = """
        SELECT c.id, c.code, c.display_name, c.active, c.sort_order,
               t.id AS current_ticket_id, t.ticket_number, t.status AS ticket_status, t.called_at
        FROM cashiers c
        LEFT JOIN queue_tickets t ON t.cashier_id = c.id AND t.status IN ('CALLED','SERVING')
        ORDER BY c.sort_order ASC, c.id ASC
    """
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql))).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "code": r.code,
                "display_name": r.display_name,
                "active": bool(r.active),
                "sort_order": r.sort_order,
                "current_ticket_id": r.current_ticket_id,
                "current_ticket": r.ticket_number,
                "current_status": r.ticket_status,
                "called_at": r.called_at.isoformat(sep=" ") if r.called_at else None,
            }
        )
    return out


async def display_state(service_date=None) -> dict:
    service_date = service_date or today_local()
    cashiers = await cashiers_state(service_date)
    async with engine.connect() as conn:
        waiting = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM queue_tickets t JOIN visits v ON v.id = t.visit_id "
                    "WHERE t.service_date = :d AND t.status = 'WAITING'"
                ),
                {"d": service_date},
            )
        ).scalar_one()
        recent = (
            await conn.execute(
                text(
                    "SELECT t.ticket_number, c.display_name, t.status, t.called_at "
                    "FROM queue_tickets t LEFT JOIN cashiers c ON c.id = t.cashier_id "
                    "WHERE t.called_at IS NOT NULL AND t.service_date = :d "
                    "ORDER BY t.called_at DESC LIMIT 8"
                ),
                {"d": service_date},
            )
        ).fetchall()
    return {
        "service_date": str(service_date),
        "waiting_count": int(waiting),
        "cashiers": cashiers,
        "recent": [
            {"ticket_number": r.ticket_number, "window": r.display_name, "status": r.status, "called_at": r.called_at.isoformat(sep=" ") if r.called_at else None}
            for r in recent
        ],
    }


async def calling_screen_state(service_date=None) -> dict:
    service_date = service_date or today_local()
    async with engine.connect() as conn:
        current = (
            await conn.execute(
                text(
                    "SELECT t.ticket_number, c.display_name, t.status, t.called_at "
                    "FROM queue_tickets t JOIN cashiers c ON c.id = t.cashier_id "
                    "WHERE t.status IN ('CALLED','SERVING') AND t.service_date = :d "
                    "ORDER BY t.called_at DESC LIMIT 1"
                ),
                {"d": service_date},
            )
        ).first()
        recent = (
            await conn.execute(
                text(
                    "SELECT a.occurred_at, a.action, t.ticket_number, c.display_name "
                    "FROM audit_events a "
                    "JOIN queue_tickets t ON t.id = a.entity_id "
                    "JOIN cashiers c ON c.id = t.cashier_id "
                    "WHERE a.action IN ('ticket.called','ticket.recalled') AND a.entity_type = 'ticket' "
                    "ORDER BY a.occurred_at DESC LIMIT 8"
                )
            )
        ).fetchall()
    return {
        "current": (
            {
                "ticket_number": current.ticket_number,
                "window": current.display_name,
                "status": current.status,
                "called_at": current.called_at.isoformat(sep=" ") if current.called_at else None,
            }
            if current is not None
            else None
        ),
        "recent": [
            {"ticket_number": r.ticket_number, "window": r.display_name, "action": r.action, "occurred_at": r.occurred_at.isoformat(sep=" ")}
            for r in recent
        ],
    }


async def public_display_state(service_date=None) -> dict:
    """Authoritative state for the public waiting-room display.

    Single source of truth: now_serving (latest CALLED/SERVING ticket),
    every active counter with its current ticket, the waiting list, and the
    missed (NO_SHOW) list. All read from MySQL.
    """
    service_date = service_date or today_local()
    cashiers = await cashiers_state(service_date)
    waiting = await waiting_queue(service_date)

    async with engine.connect() as conn:
        now_serving_row = (
            await conn.execute(
                text(
                    "SELECT t.ticket_number, t.cashier_id, c.display_name, t.called_at "
                    "FROM queue_tickets t JOIN cashiers c ON c.id = t.cashier_id "
                    "WHERE t.status IN ('CALLED','SERVING') AND t.service_date = :d "
                    "ORDER BY t.called_at DESC LIMIT 1"
                ),
                {"d": service_date},
            )
        ).first()
        missed_rows = (
            await conn.execute(
                text(
                    "SELECT t.ticket_number, c.display_name, t.called_at "
                    "FROM queue_tickets t LEFT JOIN cashiers c ON c.id = t.cashier_id "
                    "WHERE t.status = 'NO_SHOW' AND t.service_date = :d "
                    "ORDER BY t.called_at DESC"
                ),
                {"d": service_date},
            )
        ).fetchall()

    return {
        "service_date": str(service_date),
        "now_serving": (
            {
                "ticket_number": now_serving_row.ticket_number,
                "counter_id": now_serving_row.cashier_id,
                "counter_name": now_serving_row.display_name,
                "called_at": now_serving_row.called_at.isoformat(sep=" ") if now_serving_row.called_at else None,
            }
            if now_serving_row is not None
            else None
        ),
        "counters": cashiers,
        "waiting": [{"ticket_number": w["ticket_number"], "position": i + 1} for i, w in enumerate(waiting)],
        "missed": [
            {
                "ticket_number": r.ticket_number,
                "counter_name": r.display_name,
                "missed_at": r.called_at.isoformat(sep=" ") if r.called_at else None,
            }
            for r in missed_rows
        ],
    }


async def report(filters: dict) -> list[dict]:
    service_date = filters.get("service_date") or today_local()
    clauses = ["t.service_date = :d"]
    params: dict = {"d": service_date}
    if filters.get("booking_number"):
        clauses.append("a.booking_number LIKE :bn")
        params["bn"] = f"%{filters['booking_number']}%"
    if filters.get("guardian"):
        clauses.append("g.name LIKE :gn")
        params["gn"] = f"%{filters['guardian']}%"
    if filters.get("visit_type"):
        clauses.append("v.visit_type = :vt")
        params["vt"] = filters["visit_type"]
    if filters.get("cashier_id"):
        clauses.append("t.cashier_id = :cid")
        params["cid"] = filters["cashier_id"]
    if filters.get("ticket_status"):
        clauses.append("t.status = :ts")
        params["ts"] = filters["ticket_status"]
    if filters.get("appointment_status"):
        clauses.append("a.status = :as")
        params["as"] = filters["appointment_status"]

    where = " AND ".join(clauses)
    sql = f"""
        SELECT t.id, t.ticket_number, t.status AS ticket_status, t.called_at, t.service_started_at,
               t.completed_at, t.recall_count, t.cancellation_reason, t.version,
               v.service_date, v.visit_type, v.multi_appointment, v.arrival_at, v.queue_entered_at,
               g.name AS guardian_name, g.phone, g.external_guardian_id,
               c.display_name AS cashier,
               GROUP_CONCAT(DISTINCT a.booking_number ORDER BY a.id) AS booking_numbers,
               GROUP_CONCAT(DISTINCT a.external_appointment_id ORDER BY a.id) AS appointment_ids,
               GROUP_CONCAT(DISTINCT a.scheduled_at ORDER BY a.id) AS scheduled_times,
               GROUP_CONCAT(DISTINCT a.status ORDER BY a.id) AS appointment_statuses,
               GROUP_CONCAT(DISTINCT s.name ORDER BY a.id) AS student_names
        FROM queue_tickets t
        JOIN visits v ON v.id = t.visit_id
        JOIN guardians g ON g.id = v.guardian_id
        LEFT JOIN cashiers c ON c.id = t.cashier_id
        LEFT JOIN visit_appointments va ON va.visit_id = v.id
        LEFT JOIN appointments a ON a.id = va.appointment_id
        LEFT JOIN students s ON s.id = a.student_id
        WHERE {where}
        GROUP BY t.id, t.ticket_number, t.status, t.called_at, t.service_started_at, t.completed_at,
                 t.recall_count, t.cancellation_reason, t.version, v.service_date, v.visit_type,
                 v.multi_appointment, v.arrival_at, v.queue_entered_at, g.name, g.phone,
                 g.external_guardian_id, c.display_name
        ORDER BY t.ticket_number ASC
    """
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params)).fetchall()
    return [_report_row(r) for r in rows]


def _report_row(r) -> dict:
    waiting_secs = None
    if r.called_at and r.queue_entered_at:
        waiting_secs = int((r.called_at - r.queue_entered_at).total_seconds())
    service_secs = None
    if r.completed_at and r.service_started_at:
        service_secs = int((r.completed_at - r.service_started_at).total_seconds())
    return {
        "ticket_id": r.id,
        "ticket_number": r.ticket_number,
        "ticket_status": r.ticket_status,
        "service_date": str(r.service_date),
        "visit_type": r.visit_type,
        "multi_appointment": bool(r.multi_appointment),
        "guardian_name": r.guardian_name,
        "guardian_phone": r.phone,
        "guardian_external_id": r.external_guardian_id,
        "student_names": r.student_names,
        "booking_numbers": r.booking_numbers,
        "appointment_ids": r.appointment_ids,
        "scheduled_times": r.scheduled_times,
        "appointment_statuses": r.appointment_statuses,
        "arrival_at": r.arrival_at.isoformat(sep=" ") if r.arrival_at else None,
        "queue_entered_at": r.queue_entered_at.isoformat(sep=" ") if r.queue_entered_at else None,
        "called_at": r.called_at.isoformat(sep=" ") if r.called_at else None,
        "service_started_at": r.service_started_at.isoformat(sep=" ") if r.service_started_at else None,
        "completed_at": r.completed_at.isoformat(sep=" ") if r.completed_at else None,
        "waiting_seconds": waiting_secs,
        "service_seconds": service_secs,
        "recall_count": r.recall_count,
        "cancellation_reason": r.cancellation_reason,
        "cashier": r.cashier,
        "version": r.version,
    }


def _row(r) -> dict:
    return {
        "id": r.id,
        "booking_number": r.booking_number,
        "external_appointment_id": r.external_appointment_id,
        "scheduled_at": r.scheduled_at.isoformat(sep=" ") if r.scheduled_at else None,
        "status": r.status,
        "guardian_id": r.guardian_id,
        "guardian_name": r.guardian_name,
        "guardian_external_id": r.external_guardian_id,
        "phone": r.phone,
        "student_name": r.student_name,
    }
