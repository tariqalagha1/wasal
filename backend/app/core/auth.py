"""Authentication and authorization dependencies."""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.db import get_session
from app.core.security import decode_access_token
from app.models.models import Cashier, User

ROLE_RECEPTIONIST = "RECEPTIONIST"
ROLE_CASHIER = "CASHIER"
ROLE_ADMIN = "ADMIN"


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise errors.unauthenticated()
    token = auth[7:].strip()
    payload = decode_access_token(token)
    if not payload:
        raise errors.unauthenticated()
    user_id = payload.get("sub")
    if not user_id:
        raise errors.unauthenticated()
    user = await session.get(User, int(user_id))
    if user is None or not user.active:
        raise errors.unauthenticated()
    return user


async def get_optional_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
    """Like get_current_user but returns None when unauthenticated (for public endpoints)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_access_token(auth[7:].strip())
    if not payload or not payload.get("sub"):
        return None
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.active:
        return None
    return user


def require_roles(*roles: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise errors.forbidden(f"Requires role in {roles}")
        return user

    return _dep


async def get_user_station(session: AsyncSession, user: User) -> Cashier:
    """Resolve the cashier station a CASHIER user operates.

    Convention: a CASHIER user's username equals the station `code`.
    """
    res = await session.execute(
        text("SELECT id, code, display_name, active, sort_order FROM cashiers WHERE code = :code"),
        {"code": user.username},
    )
    row = res.first()
    if row is None:
        raise errors.forbidden("Cashier user has no matching station")
    return Cashier(id=row.id, code=row.code, display_name=row.display_name, active=row.active, sort_order=row.sort_order)


async def resolve_acting_station(session: AsyncSession, user: User, station_id: int | None) -> Cashier:
    """Resolve which station the acting user is allowed to operate."""
    if user.role == ROLE_ADMIN:
        if station_id is None:
            raise errors.validation_error("Admin must specify cashier station")
        res = await session.execute(
            text("SELECT id, code, display_name, active, sort_order FROM cashiers WHERE id = :id"),
            {"id": station_id},
        )
        row = res.first()
        if row is None:
            raise errors.not_found("Cashier station not found")
        return Cashier(id=row.id, code=row.code, display_name=row.display_name, active=row.active, sort_order=row.sort_order)
    if user.role == ROLE_CASHIER:
        return await get_user_station(session, user)
    raise errors.forbidden("User role cannot operate a cashier station")
