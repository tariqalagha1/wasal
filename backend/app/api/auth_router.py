"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.auth import get_current_user
from app.core.db import SessionLocal, get_session
from app.core.security import create_access_token, verify_password
from app.core.time import now_utc
from app.models.models import User
from app.services.audit_service import append_audit
from app.core.errors import new_correlation_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


async def _audit_login_failure(username: str) -> None:
    try:
        async with SessionLocal() as s:
            async with s.begin():
                await append_audit(
                    s.connection(),
                    actor_user_id=None,
                    action="user.login_failed",
                    entity_type="user",
                    entity_id=0,
                    details={"username": username},
                    correlation_id=new_correlation_id(),
                )
    except Exception:
        pass


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        text("SELECT id, username, password_hash, role, preferred_locale, active FROM users WHERE username = :u"),
        {"u": body.username},
    )
    row = res.first()
    if row is None or not verify_password(body.password, row.password_hash):
        await _audit_login_failure(body.username)
        raise errors.unauthenticated("Invalid username or password")
    if not row.active:
        raise errors.forbidden("User account is inactive")
    token = create_access_token(row.id, row.role, row.username)
    return {
        "token": token,
        "user": {"id": row.id, "username": row.username, "role": row.role, "preferred_locale": row.preferred_locale},
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "preferred_locale": user.preferred_locale,
    }
