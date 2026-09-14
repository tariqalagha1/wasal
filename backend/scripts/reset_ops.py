"""Reset operational state (keep users/cashiers/guardians/students/appointments/settings).

Non-destructive to seed/reference data. Used between test runs and for the
blind acceptance phase (clean operational state).
"""
import asyncio

from sqlalchemy import text

from app.core.db import engine

TABLES = [
    "audit_events",
    "queue_tickets",
    "visit_appointments",
    "visits",
    "daily_counters",
    "idempotency_keys",
    "import_runs",
]


async def reset_operations() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in TABLES:
            await conn.execute(text(f"DELETE FROM {t}"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        # Reset today's appointments back to SCHEDULED.
        await conn.execute(text("UPDATE appointments SET status = 'SCHEDULED' WHERE status IN ('CHECKED_IN','SERVED','CANCELLED')"))


if __name__ == "__main__":
    asyncio.run(reset_operations())
    print("operational state reset")
