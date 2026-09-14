"""Business-action transaction service.

Every state change happens through a named business action inside a single
MySQL transaction. Raw SQL is used so that row locks (FOR UPDATE / FOR UPDATE
SKIP LOCKED) and the daily ticket counter are exercised for real.

Each function returns a tuple ``(status_code, body, events)`` where ``events``
is the list of realtime notifications to publish only *after* commit.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import errors
from app.core.config import settings
from app.core.db import engine
from app.core.errors import new_correlation_id
from app.core.time import classify_arrival, local_date_of, now_utc, today_local
from app.models.models import Cashier, User
from app.services.audit_service import append_audit

_EVENT_ACTION = {
    "WAITING": None,
    "CALLED": "ticket.called",
    "SERVING": "ticket.serving",
}


async def _check_idempotency(conn, key: str):
    res = await conn.execute(
        text("SELECT response_code, response_body FROM idempotency_keys WHERE idempotency_key = :k"),
        {"k": key},
    )
    row = res.first()
    if row is None:
        return None
    body = row.response_body
    if isinstance(body, str):
        body = json.loads(body)
    return row.response_code, body


async def _store_idempotency(conn, key: str, operation: str, code: int, body: dict):
    await conn.execute(
        text(
            "INSERT INTO idempotency_keys (idempotency_key, operation, response_code, response_body, created_at) "
            "VALUES (:k, :op, :code, :body, :now)"
        ),
        {"k": key, "op": operation, "code": code, "body": json.dumps(body), "now": now_utc()},
    )


async def _allocate_ticket_number(conn, service_date) -> int:
    await conn.execute(
        text(
            "INSERT INTO daily_counters (service_date, last_ticket_number) VALUES (:d, 1) "
            "ON DUPLICATE KEY UPDATE last_ticket_number = last_ticket_number + 1"
        ),
        {"d": service_date},
    )
    num = await conn.execute(
        text("SELECT last_ticket_number FROM daily_counters WHERE service_date = :d FOR UPDATE"),
        {"d": service_date},
    )
    return num.scalar_one()


async def _resolve_guardian(conn, *, guardian_id, external_id, name, phone) -> int:
    if guardian_id is not None:
        row = (await conn.execute(text("SELECT id FROM guardians WHERE id = :id"), {"id": guardian_id})).first()
        if row is None:
            raise errors.not_found("Guardian not found")
        return row.id
    if external_id is not None:
        row = (
            await conn.execute(
                text("SELECT id FROM guardians WHERE external_guardian_id = :e"), {"e": external_id}
            )
        ).first()
        if row is not None:
            return row.id
        if not name:
            raise errors.validation_error("Guardian name required for a new guardian")
        return (
            await conn.execute(
                text("INSERT INTO guardians (external_guardian_id, name, phone) VALUES (:e, :n, :p)"),
                {"e": external_id, "n": name, "p": phone},
            )
        ).lastrowid
    if not name:
        raise errors.validation_error("Guardian name required for walk-in")
    row = (
        await conn.execute(
            text("SELECT id FROM guardians WHERE name = :n ORDER BY id LIMIT 1"), {"n": name}
        )
    ).first()
    if row is not None:
        return row.id
    return (
        await conn.execute(
            text("INSERT INTO guardians (external_guardian_id, name, phone) VALUES (NULL, :n, :p)"),
            {"n": name, "p": phone},
        )
    ).lastrowid


async def _ticket_payload(conn, ticket_id: int) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT t.id, t.ticket_number, t.status, t.cashier_id, t.visit_id, t.service_date, "
                "       t.called_at, t.service_started_at, t.completed_at, t.recall_count, t.version, "
                "       c.display_name "
                "FROM queue_tickets t LEFT JOIN cashiers c ON c.id = t.cashier_id WHERE t.id = :id"
            ),
            {"id": ticket_id},
        )
    ).first()
    return {
        "id": row.id,
        "ticket_number": row.ticket_number,
        "status": row.status,
        "cashier_id": row.cashier_id,
        "window": row.display_name,
        "visit_id": row.visit_id,
        "service_date": str(row.service_date),
        "called_at": row.called_at.isoformat(sep=" ") if row.called_at else None,
        "service_started_at": row.service_started_at.isoformat(sep=" ") if row.service_started_at else None,
        "completed_at": row.completed_at.isoformat(sep=" ") if row.completed_at else None,
        "recall_count": row.recall_count,
        "version": row.version,
    }


# ---------------------------------------------------------------------------
# Check-in
# ---------------------------------------------------------------------------
async def check_in(
    *,
    guardian_id: int | None,
    appointment_ids: list[int],
    idempotency_key: str,
    actor: User,
    notes: str | None = None,
) -> tuple[int, dict, list[dict]]:
    ids = sorted({int(x) for x in appointment_ids})
    if not ids:
        raise errors.validation_error("At least one appointment is required")

    async with engine.connect() as conn:
        async with conn.begin():
            existing = await _check_idempotency(conn, idempotency_key)
            if existing:
                return existing[0], existing[1], []

            now = now_utc()
            service_date = today_local()
            corr = new_correlation_id()

            placeholders = ", ".join(f":a{i}" for i in range(len(ids)))
            params = {f"a{i}": ids[i] for i in range(len(ids))}
            rows = (
                await conn.execute(
                    text(
                        f"SELECT id, guardian_id, scheduled_at, status, booking_number FROM appointments "
                        f"WHERE id IN ({placeholders}) FOR UPDATE"
                    ),
                    params,
                )
            ).fetchall()

            if len(rows) != len(ids):
                missing = set(ids) - {r.id for r in rows}
                raise errors.not_found(f"Appointments not found: {sorted(missing)}")

            gids = {r.guardian_id for r in rows}
            if len(gids) != 1:
                raise errors.validation_error("Selected appointments must belong to the same guardian")
            appt_guardian_id = next(iter(gids))
            if guardian_id is not None and guardian_id != appt_guardian_id:
                raise errors.validation_error("Guardian does not match selected appointments")
            guardian_id = appt_guardian_id

            for r in rows:
                if r.status != "SCHEDULED":
                    raise errors.duplicate_check_in(
                        f"Appointment {r.id} is already {r.status}",
                        {"appointment_id": r.id, "status": r.status},
                    )
                if local_date_of(r.scheduled_at) != service_date:
                    raise errors.validation_error(f"Appointment {r.id} is not for today")

            earliest = min(r.scheduled_at for r in rows)
            visit_type = classify_arrival(now, earliest)
            multi = len(ids) > 1

            ticket_number = await _allocate_ticket_number(conn, service_date)

            visit_id = (
                await conn.execute(
                    text(
                        "INSERT INTO visits (service_date, guardian_id, visit_type, multi_appointment, "
                        "arrival_at, queue_entered_at, created_by, notes) "
                        "VALUES (:d, :g, :vt, :multi, :arr, :qe, :cb, :notes)"
                    ),
                    {
                        "d": service_date,
                        "g": guardian_id,
                        "vt": visit_type,
                        "multi": multi,
                        "arr": now,
                        "qe": now,
                        "cb": actor.id,
                        "notes": notes,
                    },
                )
            ).lastrowid

            ticket_id = (
                await conn.execute(
                    text(
                        "INSERT INTO queue_tickets (visit_id, service_date, ticket_number, status) "
                        "VALUES (:v, :d, :tn, 'WAITING')"
                    ),
                    {"v": visit_id, "d": service_date, "tn": ticket_number},
                )
            ).lastrowid

            for r in rows:
                await conn.execute(
                    text("INSERT INTO visit_appointments (visit_id, appointment_id) VALUES (:v, :a)"),
                    {"v": visit_id, "a": r.id},
                )
                await conn.execute(
                    text("UPDATE appointments SET status = 'CHECKED_IN' WHERE id = :a"), {"a": r.id}
                )

            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.checked_in",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state=None,
                to_state="WAITING",
                details={"appointment_ids": ids, "visit_type": visit_type, "ticket_number": ticket_number},
                correlation_id=corr,
            )
            for r in rows:
                await append_audit(
                    conn,
                    actor_user_id=actor.id,
                    action="appointment.checked_in",
                    entity_type="appointment",
                    entity_id=r.id,
                    from_state="SCHEDULED",
                    to_state="CHECKED_IN",
                    details={"ticket_id": ticket_id, "visit_id": visit_id},
                    correlation_id=corr,
                )

            body = {
                "ticket": {"id": ticket_id, "ticket_number": ticket_number, "status": "WAITING", "service_date": str(service_date)},
                "visit": {"id": visit_id, "visit_type": visit_type, "multi_appointment": multi},
                "appointments": [{"id": r.id, "status": "CHECKED_IN"} for r in rows],
            }
            await _store_idempotency(conn, idempotency_key, "check_in", 200, body)

    return 200, body, [
        {"type": "ticket.checked_in", "entity_id": ticket_id},
        {"type": "queue.updated", "entity_id": None},
    ]


# ---------------------------------------------------------------------------
# Walk-in
# ---------------------------------------------------------------------------
async def walk_in(
    *,
    guardian_id: int | None,
    external_id: str | None,
    name: str | None,
    phone: str | None,
    idempotency_key: str,
    actor: User,
    notes: str | None = None,
) -> tuple[int, dict, list[dict]]:
    async with engine.connect() as conn:
        async with conn.begin():
            existing = await _check_idempotency(conn, idempotency_key)
            if existing:
                return existing[0], existing[1], []

            now = now_utc()
            service_date = today_local()
            corr = new_correlation_id()

            gid = await _resolve_guardian(conn, guardian_id=guardian_id, external_id=external_id, name=name, phone=phone)

            ticket_number = await _allocate_ticket_number(conn, service_date)

            visit_id = (
                await conn.execute(
                    text(
                        "INSERT INTO visits (service_date, guardian_id, visit_type, multi_appointment, "
                        "arrival_at, queue_entered_at, created_by, notes) "
                        "VALUES (:d, :g, 'WALK_IN', FALSE, :arr, :qe, :cb, :notes)"
                    ),
                    {"d": service_date, "g": gid, "arr": now, "qe": now, "cb": actor.id, "notes": notes},
                )
            ).lastrowid

            ticket_id = (
                await conn.execute(
                    text(
                        "INSERT INTO queue_tickets (visit_id, service_date, ticket_number, status) "
                        "VALUES (:v, :d, :tn, 'WAITING')"
                    ),
                    {"v": visit_id, "d": service_date, "tn": ticket_number},
                )
            ).lastrowid

            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.checked_in",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state=None,
                to_state="WAITING",
                details={"visit_type": "WALK_IN", "ticket_number": ticket_number},
                correlation_id=corr,
            )

            body = {
                "ticket": {"id": ticket_id, "ticket_number": ticket_number, "status": "WAITING", "service_date": str(service_date)},
                "visit": {"id": visit_id, "visit_type": "WALK_IN", "multi_appointment": False},
                "appointments": [],
            }
            await _store_idempotency(conn, idempotency_key, "walk_in", 200, body)

    return 200, body, [
        {"type": "ticket.checked_in", "entity_id": ticket_id},
        {"type": "queue.updated", "entity_id": None},
    ]


# ---------------------------------------------------------------------------
# Call Next
# ---------------------------------------------------------------------------
async def call_next(*, station: Cashier, actor: User) -> tuple[int, dict, list[dict]]:
    """Atomically claim the oldest eligible waiting ticket.

    The fairness SELECT orders by ``visits.queue_entered_at`` then
    ``ticket_number``. A naive ``FOR UPDATE SKIP LOCKED`` over that join with
    ``ORDER BY ... LIMIT 1`` locks *every* scanned row (not just the winner),
    which starves concurrent cashiers. Instead we (1) read the candidate id
    with a non-locking SELECT, then (2) lock exactly that one row with
    ``FOR UPDATE SKIP LOCKED``. Each attempt runs in a fresh transaction so the
    non-locking snapshot is current; a skipped/lost candidate simply retries.
    """
    for _ in range(50):
        async with engine.connect() as conn:
            async with conn.begin():
                corr = new_correlation_id()
                now = now_utc()
                service_date = today_local()

                c = (
                    await conn.execute(
                        text("SELECT id, active FROM cashiers WHERE id = :id FOR UPDATE"), {"id": station.id}
                    )
                ).first()
                if c is None:
                    raise errors.not_found("Cashier station not found")
                if not c.active:
                    raise errors.forbidden("Cashier station is inactive")

                active = (
                    await conn.execute(
                        text(
                            "SELECT id, status FROM queue_tickets WHERE cashier_id = :cid AND status IN ('CALLED','SERVING') FOR UPDATE"
                        ),
                        {"cid": station.id},
                    )
                ).first()
                if active is not None:
                    raise errors.cashier_busy(
                        f"Cashier {station.code} already has an active ticket",
                        {"ticket_id": active.id, "status": active.status},
                    )

                candidate = (
                    await conn.execute(
                        text(
                            "SELECT t.id, t.ticket_number FROM queue_tickets t "
                            "JOIN visits v ON v.id = t.visit_id "
                            "WHERE t.service_date = :d AND t.status = 'WAITING' "
                            "ORDER BY v.queue_entered_at ASC, t.ticket_number ASC LIMIT 1"
                        ),
                        {"d": service_date},
                    )
                ).first()

                if candidate is None:
                    return 200, {"result": "QUEUE_EMPTY"}, []

                locked = (
                    await conn.execute(
                        text(
                            "SELECT id, ticket_number FROM queue_tickets "
                            "WHERE id = :id AND status = 'WAITING' FOR UPDATE SKIP LOCKED"
                        ),
                        {"id": candidate.id},
                    )
                ).first()

                if locked is None:
                    # Another cashier claimed this candidate; retry in a fresh transaction.
                    continue

                await conn.execute(
                    text(
                        "UPDATE queue_tickets SET status = 'CALLED', cashier_id = :cid, called_at = :now, version = version + 1 WHERE id = :tid"
                    ),
                    {"cid": station.id, "now": now, "tid": locked.id},
                )

                await append_audit(
                    conn,
                    actor_user_id=actor.id,
                    action="ticket.called",
                    entity_type="ticket",
                    entity_id=locked.id,
                    from_state="WAITING",
                    to_state="CALLED",
                    details={"cashier_id": station.id, "ticket_number": locked.ticket_number},
                    correlation_id=corr,
                )

                body = await _ticket_payload(conn, locked.id)
                return (
                    200,
                    {"ticket": body},
                    [
                        {"type": "ticket.called", "entity_id": locked.id, "extra": {"ticket_number": locked.ticket_number, "window": station.display_name}},
                        {"type": "cashier.state_changed", "entity_id": station.id},
                        {"type": "queue.updated", "entity_id": None},
                    ],
                )

    raise errors.service_unavailable("Temporary contention while claiming a ticket; retry shortly")


# ---------------------------------------------------------------------------
# Recall / Start / Done / No-show / Return / Cancel
# ---------------------------------------------------------------------------
async def _lock_owned_ticket(conn, ticket_id: int, station: Cashier):
    t = (
        await conn.execute(
            text(
                "SELECT id, visit_id, cashier_id, status, ticket_number, version FROM queue_tickets WHERE id = :id FOR UPDATE"
            ),
            {"id": ticket_id},
        )
    ).first()
    if t is None:
        raise errors.not_found("Ticket not found")
    if t.cashier_id != station.id:
        raise errors.forbidden("Ticket is not assigned to this cashier")
    return t


async def recall(*, ticket_id: int, station: Cashier, actor: User) -> tuple[int, dict, list[dict]]:
    async with engine.connect() as conn:
        async with conn.begin():
            corr = new_correlation_id()
            now = now_utc()
            t = await _lock_owned_ticket(conn, ticket_id, station)
            if t.status != "CALLED":
                raise errors.invalid_transition("Only a CALLED ticket can be recalled", {"status": t.status})

            await conn.execute(
                text(
                    "UPDATE queue_tickets SET recall_count = recall_count + 1, called_at = :now, version = version + 1 WHERE id = :id"
                ),
                {"now": now, "id": ticket_id},
            )
            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.recalled",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state="CALLED",
                to_state="CALLED",
                details={"cashier_id": station.id, "ticket_number": t.ticket_number},
                correlation_id=corr,
            )
            body = await _ticket_payload(conn, ticket_id)

    return 200, {"ticket": body}, [
        {"type": "ticket.recalled", "entity_id": ticket_id, "extra": {"ticket_number": t.ticket_number, "window": station.display_name}},
    ]


async def start_serving(*, ticket_id: int, station: Cashier, actor: User) -> tuple[int, dict, list[dict]]:
    async with engine.connect() as conn:
        async with conn.begin():
            corr = new_correlation_id()
            now = now_utc()
            t = await _lock_owned_ticket(conn, ticket_id, station)
            if t.status != "CALLED":
                raise errors.invalid_transition("Only a CALLED ticket can start serving", {"status": t.status})

            await conn.execute(
                text(
                    "UPDATE queue_tickets SET status = 'SERVING', service_started_at = :now, version = version + 1 WHERE id = :id"
                ),
                {"now": now, "id": ticket_id},
            )
            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.serving",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state="CALLED",
                to_state="SERVING",
                details={"cashier_id": station.id, "ticket_number": t.ticket_number},
                correlation_id=corr,
            )
            body = await _ticket_payload(conn, ticket_id)

    return 200, {"ticket": body}, [
        {"type": "ticket.serving", "entity_id": ticket_id},
        {"type": "cashier.state_changed", "entity_id": station.id},
    ]


async def complete(*, ticket_id: int, station: Cashier, actor: User) -> tuple[int, dict, list[dict]]:
    async with engine.connect() as conn:
        async with conn.begin():
            corr = new_correlation_id()
            now = now_utc()
            t = await _lock_owned_ticket(conn, ticket_id, station)
            if t.status != "SERVING":
                raise errors.invalid_transition("Only a SERVING ticket can be completed", {"status": t.status})

            # Lock visit, cashier, and selected appointments as required.
            await conn.execute(text("SELECT id FROM visits WHERE id = :id FOR UPDATE"), {"id": t.visit_id})
            await conn.execute(text("SELECT id FROM cashiers WHERE id = :id FOR UPDATE"), {"id": station.id})
            appts = (
                await conn.execute(
                    text(
                        "SELECT a.id FROM appointments a JOIN visit_appointments va ON va.appointment_id = a.id "
                        "WHERE va.visit_id = :vid FOR UPDATE"
                    ),
                    {"vid": t.visit_id},
                )
            ).fetchall()

            await conn.execute(
                text(
                    "UPDATE queue_tickets SET status = 'DONE', completed_at = :now, version = version + 1 WHERE id = :id"
                ),
                {"now": now, "id": ticket_id},
            )
            for a in appts:
                await conn.execute(text("UPDATE appointments SET status = 'SERVED' WHERE id = :id"), {"id": a.id})

            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.completed",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state="SERVING",
                to_state="DONE",
                details={"cashier_id": station.id, "ticket_number": t.ticket_number, "served_appointments": [a.id for a in appts]},
                correlation_id=corr,
            )
            for a in appts:
                await append_audit(
                    conn,
                    actor_user_id=actor.id,
                    action="appointment.served",
                    entity_type="appointment",
                    entity_id=a.id,
                    from_state="CHECKED_IN",
                    to_state="SERVED",
                    details={"ticket_id": ticket_id},
                    correlation_id=corr,
                )
            body = await _ticket_payload(conn, ticket_id)

    return 200, {"ticket": body, "served_appointments": [a.id for a in appts]}, [
        {"type": "ticket.completed", "entity_id": ticket_id},
        {"type": "cashier.state_changed", "entity_id": station.id},
        {"type": "queue.updated", "entity_id": None},
    ]


async def no_show(*, ticket_id: int, station: Cashier, actor: User, reason: str | None = None) -> tuple[int, dict, list[dict]]:
    async with engine.connect() as conn:
        async with conn.begin():
            corr = new_correlation_id()
            t = await _lock_owned_ticket(conn, ticket_id, station)
            if t.status != "CALLED":
                raise errors.invalid_transition("Only a CALLED ticket can be marked no-show", {"status": t.status})

            await conn.execute(
                text("UPDATE queue_tickets SET status = 'NO_SHOW', version = version + 1 WHERE id = :id"),
                {"id": ticket_id},
            )
            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.no_show",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state="CALLED",
                to_state="NO_SHOW",
                details={"cashier_id": station.id, "ticket_number": t.ticket_number, "reason": reason},
                correlation_id=corr,
            )
            body = await _ticket_payload(conn, ticket_id)

    return 200, {"ticket": body}, [
        {"type": "ticket.no_show", "entity_id": ticket_id},
        {"type": "cashier.state_changed", "entity_id": station.id},
        {"type": "queue.updated", "entity_id": None},
    ]


async def return_to_queue(*, ticket_id: int, actor: User) -> tuple[int, dict, list[dict]]:
    async with engine.connect() as conn:
        async with conn.begin():
            corr = new_correlation_id()
            now = now_utc()
            t = (
                await conn.execute(
                    text("SELECT id, visit_id, status, ticket_number, version FROM queue_tickets WHERE id = :id FOR UPDATE"),
                    {"id": ticket_id},
                )
            ).first()
            if t is None:
                raise errors.not_found("Ticket not found")
            if t.status != "NO_SHOW":
                raise errors.invalid_transition("Only a NO_SHOW ticket can return to queue", {"status": t.status})

            await conn.execute(
                text(
                    "UPDATE queue_tickets SET status = 'WAITING', cashier_id = NULL, called_at = NULL, "
                    "service_started_at = NULL, completed_at = NULL, version = version + 1 WHERE id = :id"
                ),
                {"id": ticket_id},
            )
            await conn.execute(
                text("UPDATE visits SET queue_entered_at = :now WHERE id = :vid"),
                {"now": now, "vid": t.visit_id},
            )
            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.returned_to_queue",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state="NO_SHOW",
                to_state="WAITING",
                details={"ticket_number": t.ticket_number},
                correlation_id=corr,
            )
            body = await _ticket_payload(conn, ticket_id)

    return 200, {"ticket": body}, [
        {"type": "ticket.returned_to_queue", "entity_id": ticket_id},
        {"type": "queue.updated", "entity_id": None},
    ]


async def cancel(*, ticket_id: int, actor: User, reason: str) -> tuple[int, dict, list[dict]]:
    if not reason or not reason.strip():
        raise errors.validation_error("Cancellation reason is required")

    async with engine.connect() as conn:
        async with conn.begin():
            corr = new_correlation_id()
            t = (
                await conn.execute(
                    text("SELECT id, visit_id, status, ticket_number, cashier_id, version FROM queue_tickets WHERE id = :id FOR UPDATE"),
                    {"id": ticket_id},
                )
            ).first()
            if t is None:
                raise errors.not_found("Ticket not found")
            if t.status not in ("WAITING", "CALLED"):
                raise errors.invalid_transition("Only a WAITING or CALLED ticket can be cancelled", {"status": t.status})

            await conn.execute(
                text(
                    "UPDATE queue_tickets SET status = 'CANCELLED', cashier_id = NULL, cancellation_reason = :reason, version = version + 1 WHERE id = :id"
                ),
                {"reason": reason.strip(), "id": ticket_id},
            )
            # Revert any CHECKED_IN appointments linked to this visit back to SCHEDULED
            # so the guardian remains serviceable. History stays in audit_events.
            appts = (
                await conn.execute(
                    text(
                        "SELECT a.id FROM appointments a JOIN visit_appointments va ON va.appointment_id = a.id "
                        "WHERE va.visit_id = :vid AND a.status = 'CHECKED_IN' FOR UPDATE"
                    ),
                    {"vid": t.visit_id},
                )
            ).fetchall()
            for a in appts:
                await conn.execute(text("UPDATE appointments SET status = 'SCHEDULED' WHERE id = :id"), {"id": a.id})
                await append_audit(
                    conn,
                    actor_user_id=actor.id,
                    action="appointment.reverted",
                    entity_type="appointment",
                    entity_id=a.id,
                    from_state="CHECKED_IN",
                    to_state="SCHEDULED",
                    details={"ticket_id": ticket_id, "reason": reason.strip()},
                    correlation_id=corr,
                )

            await append_audit(
                conn,
                actor_user_id=actor.id,
                action="ticket.cancelled",
                entity_type="ticket",
                entity_id=ticket_id,
                from_state=t.status,
                to_state="CANCELLED",
                details={"ticket_number": t.ticket_number, "reason": reason.strip()},
                correlation_id=corr,
            )
            body = await _ticket_payload(conn, ticket_id)

    return 200, {"ticket": body}, [
        {"type": "ticket.cancelled", "entity_id": ticket_id},
        {"type": "queue.updated", "entity_id": None},
    ]
