"""Reception endpoints: check-in and walk-in."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core import errors
from app.core.auth import get_current_user, require_roles
from app.models.models import User
from app.api.common import publish_events
from app.services import transition_service

router = APIRouter(prefix="/api", tags=["reception"])


class CheckInRequest(BaseModel):
    guardian_id: int | None = None
    appointment_ids: list[int]
    notes: str | None = None


class WalkInRequest(BaseModel):
    guardian_id: int | None = None
    external_id: str | None = None
    name: str | None = None
    phone: str | None = None
    notes: str | None = None


@router.post("/check-ins")
async def check_in(
    body: CheckInRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(require_roles("RECEPTIONIST", "ADMIN")),
):
    if not idempotency_key:
        raise errors.validation_error("Idempotency-Key header is required")
    code, resp, events = await transition_service.check_in(
        guardian_id=body.guardian_id,
        appointment_ids=body.appointment_ids,
        idempotency_key=idempotency_key,
        actor=user,
        notes=body.notes,
    )
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


@router.post("/walk-ins")
async def walk_in(
    body: WalkInRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(require_roles("RECEPTIONIST", "ADMIN")),
):
    if not idempotency_key:
        raise errors.validation_error("Idempotency-Key header is required")
    code, resp, events = await transition_service.walk_in(
        guardian_id=body.guardian_id,
        external_id=body.external_id,
        name=body.name,
        phone=body.phone,
        idempotency_key=idempotency_key,
        actor=user,
        notes=body.notes,
    )
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)
