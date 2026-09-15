"""QMS V1 FastAPI application entrypoint."""
from __future__ import annotations

import contextlib
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import admin_router, appointments_router, auth_router, cashier_router, display_config_router, display_router, reception_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.migrations import apply_migrations
from app.core.realtime import manager


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await apply_migrations()
    from app.seed import seed_if_empty

    await seed_if_empty()
    yield


app = FastAPI(title="QMS V1", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(auth_router.router)
app.include_router(appointments_router.router)
app.include_router(reception_router.router)
app.include_router(cashier_router.router)
app.include_router(display_router.router)
app.include_router(display_config_router.router)
app.include_router(admin_router.router)

# Uploaded display assets (logos/images) — served statically.
_upload_dir = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(_upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_dir), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep the socket alive; clients re-fetch authoritative state on reconnect.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
