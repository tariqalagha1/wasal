"""Cashier lifecycle and concurrency endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.auth import get_current_user, get_user_station, require_roles
from app.core.db import get_session
from app.models.models import Cashier, User
from app.api.common import publish_events
from app.services import query_service, transition_service

router = APIRouter(prefix="/api", tags=["cashier"])


async def _acting_station_for_ticket(session: AsyncSession, user: User, ticket_id: int) -> Cashier:
    """Resolve the station a cashier/admin acts as for a ticket-level action."""
    if user.role == "ADMIN":
        res = await session.execute(text("SELECT cashier_id FROM queue_tickets WHERE id = :id"), {"id": ticket_id})
        row = res.first()
        if row is None or row.cashier_id is None:
            raise errors.not_found("Ticket not found or not assigned to a cashier")
        res2 = await session.execute(
            text("SELECT id, code, display_name, active, sort_order FROM cashiers WHERE id = :id"),
            {"id": row.cashier_id},
        )
        r2 = res2.first()
        if r2 is None:
            raise errors.not_found("Cashier station not found")
        return Cashier(id=r2.id, code=r2.code, display_name=r2.display_name, active=r2.active, sort_order=r2.sort_order)
    return await get_user_station(session, user)


@router.get("/queue/waiting")
async def waiting(user: User = Depends(require_roles("RECEPTIONIST", "CASHIER", "ADMIN"))):
    return {"waiting": await query_service.waiting_queue()}


@router.get("/cashiers")
async def list_cashiers(user: User = Depends(require_roles("RECEPTIONIST", "CASHIER", "ADMIN"))):
    return {"cashiers": await query_service.cashiers_state()}


@router.post("/cashiers/{cashier_id}/call-next")
async def call_next(
    cashier_id: int,
    user: User = Depends(require_roles("CASHIER", "ADMIN")),
    session: AsyncSession = Depends(get_session),
):
    if user.role == "CASHIER":
        station = await get_user_station(session, user)
        if station.id != cashier_id:
            raise errors.forbidden("Cashier may only call next on their own station")
    else:
        res = await session.execute(
            text("SELECT id, code, display_name, active, sort_order FROM cashiers WHERE id = :id"), {"id": cashier_id}
        )
        row = res.first()
        if row is None:
            raise errors.not_found("Cashier station not found")
        station = Cashier(id=row.id, code=row.code, display_name=row.display_name, active=row.active, sort_order=row.sort_order)

    code, resp, events = await transition_service.call_next(station=station, actor=user)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


class NoShowRequest(BaseModel):
    reason: str | None = None


class CancelRequest(BaseModel):
    reason: str


@router.post("/tickets/{ticket_id}/recall")
async def recall(ticket_id: int, user: User = Depends(require_roles("CASHIER", "ADMIN")), session: AsyncSession = Depends(get_session)):
    station = await _acting_station_for_ticket(session, user, ticket_id)
    code, resp, events = await transition_service.recall(ticket_id=ticket_id, station=station, actor=user)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


@router.post("/tickets/{ticket_id}/start")
async def start(ticket_id: int, user: User = Depends(require_roles("CASHIER", "ADMIN")), session: AsyncSession = Depends(get_session)):
    station = await _acting_station_for_ticket(session, user, ticket_id)
    code, resp, events = await transition_service.start_serving(ticket_id=ticket_id, station=station, actor=user)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


@router.post("/tickets/{ticket_id}/done")
async def done(ticket_id: int, user: User = Depends(require_roles("CASHIER", "ADMIN")), session: AsyncSession = Depends(get_session)):
    station = await _acting_station_for_ticket(session, user, ticket_id)
    code, resp, events = await transition_service.complete(ticket_id=ticket_id, station=station, actor=user)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


@router.post("/tickets/{ticket_id}/no-show")
async def no_show(ticket_id: int, body: NoShowRequest | None = None, user: User = Depends(require_roles("CASHIER", "ADMIN")), session: AsyncSession = Depends(get_session)):
    station = await _acting_station_for_ticket(session, user, ticket_id)
    code, resp, events = await transition_service.no_show(ticket_id=ticket_id, station=station, actor=user, reason=body.reason if body else None)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


@router.post("/tickets/{ticket_id}/return-to-queue")
async def return_to_queue(ticket_id: int, user: User = Depends(require_roles("RECEPTIONIST", "ADMIN"))):
    code, resp, events = await transition_service.return_to_queue(ticket_id=ticket_id, actor=user)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)


@router.post("/tickets/{ticket_id}/cancel")
async def cancel(ticket_id: int, body: CancelRequest, user: User = Depends(require_roles("RECEPTIONIST", "ADMIN"))):
    code, resp, events = await transition_service.cancel(ticket_id=ticket_id, actor=user, reason=body.reason)
    await publish_events(events)
    return JSONResponse(status_code=code, content=resp)
