"""Pytest fixtures. Tests run against a real MySQL 8 instance (qms_test)."""
import os

# Point the app at the isolated test database BEFORE importing any app module.
os.environ["DATABASE_URL"] = "mysql+asyncmy://qms_user:qms_pass@127.0.0.1:3307/qms_test?charset=utf8mb4"
os.environ.setdefault("JWT_SECRET", "test_secret_change_me")
os.environ["QMS_TESTING"] = "1"

import asyncio  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.migrations import apply_migrations  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.core.time import today_local  # noqa: E402
from app.seed import _seed_records  # noqa: E402
from app.services import import_service  # noqa: E402

# Stable user ids from seed order (admin, reception, WIN1..WIN4).
ADMIN_ID = 1
RECEPTION_ID = 2
WIN_IDS = {1: 3, 2: 4, 3: 5, 4: 6}


@pytest.fixture(scope="session", autouse=True)
async def init_db():
    await apply_migrations()
    from app.seed import seed_if_empty

    await seed_if_empty()
    yield


async def _reset_ops():
    from sqlalchemy import text

    from app.core.db import engine

    tables = [
        "audit_events",
        "queue_tickets",
        "visit_appointments",
        "visits",
        "daily_counters",
        "idempotency_keys",
        "import_runs",
    ]
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in tables:
            await conn.execute(text(f"DELETE FROM {t}"))
        await conn.execute(text("DELETE FROM appointments"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


@pytest.fixture(autouse=True)
async def fresh_state():
    """Reset operational state + reseed today's appointments before every test."""
    await _reset_ops()
    await import_service.import_records(service_date=today_local(), source_system="seed", records=_seed_records(today_local()))
    yield


def make_token(user_id: int, role: str, username: str) -> str:
    return create_access_token(user_id, role, username)


def tokens() -> dict:
    return {
        "admin": make_token(ADMIN_ID, "ADMIN", "admin"),
        "reception": make_token(RECEPTION_ID, "RECEPTIONIST", "reception"),
        **{f"WIN{i}": make_token(WIN_IDS[i], "CASHIER", f"WIN{i}") for i in range(1, 5)},
    }


@pytest.fixture
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def auth():
    return tokens()


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
