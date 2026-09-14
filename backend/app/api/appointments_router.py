"""Appointment read endpoints (reception)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, require_roles
from app.models.models import User
from app.services import query_service

router = APIRouter(prefix="/api", tags=["appointments"])


@router.get("/appointments/today")
async def list_today(
    search: str | None = Query(default=None),
    user: User = Depends(require_roles("RECEPTIONIST", "CASHIER", "ADMIN")),
):
    return {"appointments": await query_service.today_appointments(search=search)}


@router.get("/guardians/{guardian_id}/appointments/today")
async def guardian_today(
    guardian_id: int,
    user: User = Depends(require_roles("RECEPTIONIST", "ADMIN")),
):
    return {"appointments": await query_service.guardian_appointments_today(guardian_id)}
