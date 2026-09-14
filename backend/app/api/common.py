"""Shared API helpers."""
from __future__ import annotations

from app.core.realtime import manager


async def publish_events(events: list[dict]) -> None:
    for e in events:
        await manager.broadcast(e["type"], e.get("entity_id"), version=e.get("version"), extra=e.get("extra"))
