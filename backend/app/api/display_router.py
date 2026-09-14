"""Public display, calling screen, and language-settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.auth import get_current_user, get_optional_user
from app.core.db import get_session
from app.core.time import now_utc
from app.models.models import User
from app.services import query_service

router = APIRouter(prefix="/api", tags=["display"])

_PUBLIC_SCOPE_TO_KEY = {"public_display": "public_display_locale", "calling_screen": "calling_screen_locale"}


async def _get_setting(session: AsyncSession, key: str, default: str) -> str:
    res = await session.execute(text("SELECT setting_value FROM system_settings WHERE setting_key = :k"), {"k": key})
    row = res.first()
    if row is None:
        return default
    val = row.setting_value
    if isinstance(val, str):
        import json

        val = json.loads(val)
    return val.get("locale", default)


@router.get("/display/state")
async def display_state():
    return await query_service.display_state()


@router.get("/calling-screen/state")
async def calling_screen_state():
    return await query_service.calling_screen_state()


class LanguagePut(BaseModel):
    scope: str  # user | public_display | calling_screen
    locale: str  # en | ar


@router.get("/settings/language")
async def get_language(
    scope: str = Query(default="user"),
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
):
    if scope in _PUBLIC_SCOPE_TO_KEY:
        locale = await _get_setting(session, _PUBLIC_SCOPE_TO_KEY[scope], "en")
        return {"scope": scope, "locale": locale}
    if scope == "user":
        if user is None:
            raise errors.unauthenticated()
        return {"scope": "user", "locale": user.preferred_locale}
    raise errors.validation_error(f"Unknown scope: {scope}")


@router.put("/settings/language")
async def put_language(
    body: LanguagePut,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.locale not in ("en", "ar"):
        raise errors.validation_error("locale must be 'en' or 'ar'")
    if body.scope == "user":
        await session.execute(text("UPDATE users SET preferred_locale = :l WHERE id = :id"), {"l": body.locale, "id": user.id})
        await session.commit()
        return {"scope": "user", "locale": body.locale}
    if body.scope in _PUBLIC_SCOPE_TO_KEY:
        if user.role != "ADMIN":
            raise errors.forbidden("Only admin can change public display language")
        key = _PUBLIC_SCOPE_TO_KEY[body.scope]
        await session.execute(
            text(
                "INSERT INTO system_settings (setting_key, setting_value, updated_at, updated_by) "
                "VALUES (:k, :v, :now, :uid) AS new "
                "ON DUPLICATE KEY UPDATE setting_value = new.setting_value, updated_at = new.updated_at, updated_by = new.updated_by"
            ),
            {"k": key, "v": '{"locale": "' + body.locale + '"}', "now": now_utc(), "uid": user.id},
        )
        await session.commit()
        return {"scope": body.scope, "locale": body.locale}
    raise errors.validation_error(f"Unknown scope: {body.scope}")
