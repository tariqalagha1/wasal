"""In-process WebSocket connection manager.

WebSocket messages are notifications only — MySQL is the source of truth.
A single backend instance owns the manager; clients re-fetch authoritative
REST state on reconnect.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, type_: str, entity_id: int | None, version: int | None = None, extra: dict | None = None) -> None:
        event = {
            "event_id": uuid.uuid4().hex,
            "type": type_,
            "occurred_at": _now_iso(),
            "entity_id": entity_id,
            "version": version,
        }
        if extra:
            event.update(extra)
        message = json.dumps(event)
        async with self._lock:
            targets = list(self._connections)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


def _now_iso() -> str:
    from app.core.time import now_utc

    return now_utc().isoformat(sep=" ")


manager = ConnectionManager()
