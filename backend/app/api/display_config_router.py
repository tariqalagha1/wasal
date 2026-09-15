"""Display configuration CRUD + logo upload endpoints.

Draft/publish model: the admin edits a draft, previews it, then publishes. The
public display reads only the published configuration. Uploaded images are
stored persistently under ``UPLOAD_DIR`` and served at ``/uploads/...``.
"""
from __future__ import annotations

import json
import os
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.auth import get_current_user
from app.core.db import get_session
from app.core.time import now_utc
from app.models.models import User
from app.services import display_config

router = APIRouter(prefix="/api", tags=["display-config"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


async def _read_config(session: AsyncSession, key: str) -> dict | None:
    res = await session.execute(
        text("SELECT setting_value FROM system_settings WHERE setting_key = :k"), {"k": key}
    )
    row = res.first()
    if row is None:
        return None
    val = row.setting_value
    if isinstance(val, str):
        val = json.loads(val)
    return val if isinstance(val, dict) else None


async def _write_config(session: AsyncSession, key: str, config: dict, user_id: int) -> None:
    await session.execute(
        text(
            "INSERT INTO system_settings (setting_key, setting_value, updated_at, updated_by) "
            "VALUES (:k, :v, :now, :uid) AS new "
            "ON DUPLICATE KEY UPDATE setting_value = new.setting_value, updated_at = new.updated_at, updated_by = new.updated_by"
        ),
        {"k": key, "v": json.dumps(config), "now": now_utc(), "uid": user_id},
    )


def _fill_defaults(config: dict) -> dict:
    """Merge a submitted config over the default so missing fields are safe."""
    base = display_config.deep_preset("default")
    if not isinstance(config, dict):
        return base
    base.update(config)
    base["widgets"] = {**base.get("widgets", {}), **config.get("widgets", {})}
    base["identity"] = {**base.get("identity", {}), **config.get("identity", {})}
    return base


@router.get("/display-config")
async def get_published(session: AsyncSession = Depends(get_session)):
    cfg = await _read_config(session, display_config.PUBLISHED_KEY)
    if cfg is None:
        cfg = display_config.deep_preset("default")
    return cfg


@router.get("/display-config/draft")
async def get_draft(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if user.role != "ADMIN":
        raise errors.forbidden("Only admin can access the display designer")
    cfg = await _read_config(session, display_config.DRAFT_KEY)
    if cfg is None:
        cfg = await _read_config(session, display_config.PUBLISHED_KEY)
    if cfg is None:
        cfg = display_config.deep_preset("default")
    return cfg


class ConfigPut(BaseModel):
    config: dict


@router.put("/display-config/draft")
async def put_draft(
    body: ConfigPut,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role != "ADMIN":
        raise errors.forbidden("Only admin can edit the display designer")
    cfg = _fill_defaults(body.config)
    await _write_config(session, display_config.DRAFT_KEY, cfg, user.id)
    await session.commit()
    return {"saved": True, "config": cfg}


@router.post("/display-config/publish")
async def publish(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role != "ADMIN":
        raise errors.forbidden("Only admin can publish the display design")
    draft = await _read_config(session, display_config.DRAFT_KEY)
    if draft is None:
        draft = await _read_config(session, display_config.PUBLISHED_KEY)
    if draft is None:
        draft = display_config.deep_preset("default")
    await _write_config(session, display_config.PUBLISHED_KEY, draft, user.id)
    await session.commit()
    return {"published": True, "config": draft}


class ResetBody(BaseModel):
    preset: str = "default"


@router.post("/display-config/reset")
async def reset(
    body: ResetBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role != "ADMIN":
        raise errors.forbidden("Only admin can reset the display design")
    cfg = display_config.deep_preset(body.preset)
    await _write_config(session, display_config.DRAFT_KEY, cfg, user.id)
    await session.commit()
    return {"reset": True, "preset": body.preset, "config": cfg}


@router.post("/uploads")
async def upload_logo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    if user.role != "ADMIN":
        raise errors.forbidden("Only admin can upload images")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise errors.validation_error("Image too large (max 5 MB)")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
        raise errors.validation_error("Unsupported image type")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as fh:
        fh.write(data)
    return {"url": f"/uploads/{fname}"}
