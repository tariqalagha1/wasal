"""Append-only audit event writer.

Audit events are written inside the same MySQL transaction as the business
action that produced them, so a material action and its audit record commit
atomically. Writes use raw SQL via the caller's connection.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.time import now_utc


async def append_audit(
    conn: AsyncConnection,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int,
    from_state: str | None = None,
    to_state: str | None = None,
    details: dict | None = None,
    correlation_id: str,
    occurred_at=None,
) -> None:
    occurred_at = occurred_at or now_utc()
    await conn.execute(
        text(
            """
            INSERT INTO audit_events
              (occurred_at, actor_user_id, action, entity_type, entity_id, from_state, to_state, details, correlation_id)
            VALUES
              (:occurred_at, :actor, :action, :entity_type, :entity_id, :from_state, :to_state, :details, :correlation_id)
            """
        ),
        {
            "occurred_at": occurred_at,
            "actor": actor_user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "from_state": from_state,
            "to_state": to_state,
            "details": json.dumps(details) if details is not None else None,
            "correlation_id": correlation_id,
        },
    )
