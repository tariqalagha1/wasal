"""Admin endpoints: import, reports, audit, and user/cashier management."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.db import get_session
from app.core.security import hash_password
from app.core.time import now_utc, today_local
from app.models.models import User
from app.services import import_service, query_service

router = APIRouter(prefix="/api", tags=["admin"])


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
@router.post("/imports/today")
async def trigger_import(user: User = Depends(require_roles("ADMIN"))):
    service_date = today_local()
    records = import_service.demo_records(service_date)
    summary = await import_service.import_records(service_date=service_date, source_system="demo", records=records, actor_user_id=user.id)
    return summary


@router.get("/imports")
async def import_history(user: User = Depends(require_roles("ADMIN")), session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        text(
            "SELECT id, service_date, source_system, started_at, completed_at, status, read_count, "
            "inserted_count, updated_count, rejected_count, error_summary FROM import_runs ORDER BY id DESC LIMIT 50"
        )
    )
    rows = res.fetchall()
    return {
        "imports": [
            {
                "id": r.id,
                "service_date": str(r.service_date),
                "source_system": r.source_system,
                "started_at": r.started_at.isoformat(sep=" ") if r.started_at else None,
                "completed_at": r.completed_at.isoformat(sep=" ") if r.completed_at else None,
                "status": r.status,
                "read_count": r.read_count,
                "inserted_count": r.inserted_count,
                "updated_count": r.updated_count,
                "rejected_count": r.rejected_count,
                "error_summary": r.error_summary,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@router.get("/reports/appointments")
async def report_json(
    service_date: str | None = Query(default=None),
    booking_number: str | None = Query(default=None),
    guardian: str | None = Query(default=None),
    visit_type: str | None = Query(default=None),
    cashier_id: int | None = Query(default=None),
    ticket_status: str | None = Query(default=None),
    appointment_status: str | None = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
):
    rows = await query_service.report(
        {
            "service_date": service_date,
            "booking_number": booking_number,
            "guardian": guardian,
            "visit_type": visit_type,
            "cashier_id": cashier_id,
            "ticket_status": ticket_status,
            "appointment_status": appointment_status,
        }
    )
    return {"rows": rows, "count": len(rows)}


@router.get("/reports/appointments.csv")
async def report_csv(
    service_date: str | None = Query(default=None),
    user: User = Depends(require_roles("ADMIN")),
):
    rows = await query_service.report({"service_date": service_date})
    buf = io.StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = ["ticket_number", "guardian_name", "visit_type", "ticket_status"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=appointments.csv"},
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
@router.get("/audit")
async def audit(
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    user: User = Depends(require_roles("ADMIN")),
    session: AsyncSession = Depends(get_session),
):
    clauses = ["1=1"]
    params: dict = {}
    if entity_type:
        clauses.append("entity_type = :et")
        params["et"] = entity_type
    if entity_id:
        clauses.append("entity_id = :eid")
        params["eid"] = entity_id
    if action:
        clauses.append("action = :a")
        params["a"] = action
    where = " AND ".join(clauses)
    res = await session.execute(
        text(
            f"SELECT id, occurred_at, actor_user_id, action, entity_type, entity_id, from_state, to_state, details, correlation_id "
            f"FROM audit_events WHERE {where} ORDER BY id DESC LIMIT :lim"
        ),
        {**params, "lim": limit},
    )
    rows = res.fetchall()
    return {
        "audit": [
            {
                "id": r.id,
                "occurred_at": r.occurred_at.isoformat(sep=" ") if r.occurred_at else None,
                "actor_user_id": r.actor_user_id,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "from_state": r.from_state,
                "to_state": r.to_state,
                "details": r.details,
                "correlation_id": r.correlation_id,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# User / cashier management
# ---------------------------------------------------------------------------
class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str  # RECEPTIONIST | CASHIER | ADMIN
    preferred_locale: str = "en"


@router.get("/users")
async def list_users(user: User = Depends(require_roles("ADMIN")), session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        text("SELECT id, username, role, preferred_locale, active, created_at FROM users ORDER BY id")
    )
    rows = res.fetchall()
    return {
        "users": [
            {
                "id": r.id,
                "username": r.username,
                "role": r.role,
                "preferred_locale": r.preferred_locale,
                "active": bool(r.active),
            }
            for r in rows
        ]
    }


@router.post("/users")
async def create_user(body: CreateUserRequest, user: User = Depends(require_roles("ADMIN")), session: AsyncSession = Depends(get_session)):
    if body.role not in ("RECEPTIONIST", "CASHIER", "ADMIN"):
        return Response(status_code=400, content='{"error":{"code":"VALIDATION_ERROR","message":"Invalid role"}}', media_type="application/json")
    await session.execute(
        text("INSERT INTO users (username, password_hash, role, preferred_locale, active) VALUES (:u, :p, :r, :l, TRUE)"),
        {"u": body.username, "p": hash_password(body.password), "r": body.role, "l": body.preferred_locale},
    )
    await session.commit()
    return {"created": body.username}


@router.get("/admin/cashiers")
async def list_cashiers_admin(user: User = Depends(require_roles("ADMIN")), session: AsyncSession = Depends(get_session)):
    res = await session.execute(text("SELECT id, code, display_name, active, sort_order FROM cashiers ORDER BY sort_order"))
    rows = res.fetchall()
    return {"cashiers": [{"id": r.id, "code": r.code, "display_name": r.display_name, "active": bool(r.active), "sort_order": r.sort_order} for r in rows]}


class CreateCashierRequest(BaseModel):
    code: str
    display_name: str
    sort_order: int


@router.post("/admin/cashiers")
async def create_cashier(body: CreateCashierRequest, user: User = Depends(require_roles("ADMIN")), session: AsyncSession = Depends(get_session)):
    await session.execute(
        text("INSERT INTO cashiers (code, display_name, active, sort_order) VALUES (:c, :d, TRUE, :s)"),
        {"c": body.code, "d": body.display_name, "s": body.sort_order},
    )
    await session.commit()
    return {"created": body.code}
