"""C01, C02 — daily import and idempotent retry.

Each test uses a unique source_system + external-id prefix so the seed fixture's
records never collide with a test's own imports (the fresh-state fixture does
not delete appointments).
"""
import pytest
from sqlalchemy import text

from app.core.db import engine
from app.core.time import today_local
from app.seed import _seed_records
from app.services import import_service


def _records(token: str) -> list[dict]:
    recs = _seed_records(today_local())
    for r in recs:
        r["external_appointment_id"] = f"{token}-{r['external_appointment_id']}"
    return recs


@pytest.mark.asyncio
async def test_c01_morning_import_maps_correctly():
    d = today_local()
    source = "import_test_c01"
    records = _records("c01")
    summary = await import_service.import_records(service_date=d, source_system=source, records=records)
    assert summary["status"] in ("SUCCEEDED", "PARTIAL")
    assert summary["inserted"] == len(records)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT a.booking_number, a.scheduled_at, g.name AS guardian, s.name AS student "
                    "FROM appointments a JOIN guardians g ON g.id = a.guardian_id "
                    "LEFT JOIN students s ON s.id = a.student_id WHERE a.source_system = :s"
                ),
                {"s": source},
            )
        ).fetchall()
    assert len(rows) == len(records)  # >= 20 appointments
    for r in rows:
        assert r.booking_number and r.guardian and r.student and r.scheduled_at


@pytest.mark.asyncio
async def test_c02_import_retry_no_duplicates():
    d = today_local()
    source = "import_test_c02"
    records = _records("c02")
    first = await import_service.import_records(service_date=d, source_system=source, records=records)
    second = await import_service.import_records(service_date=d, source_system=source, records=records)

    assert first["inserted"] == len(records)
    assert second["inserted"] == 0  # no duplicates on identical retry

    async with engine.connect() as conn:
        count = (
            await conn.execute(text("SELECT COUNT(*) FROM appointments WHERE source_system = :s"), {"s": source})
        ).scalar_one()
    assert count == len(records)


@pytest.mark.asyncio
async def test_import_update_safety_preserves_served():
    d = today_local()
    source = "import_test_us"
    records = _records("us")
    await import_service.import_records(service_date=d, source_system=source, records=records)

    # Mark one appointment SERVED (simulating completed service).
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE appointments SET status = 'SERVED' WHERE external_appointment_id = 'us-SEED-001'"))

    # Re-import with a source cancellation; must NOT revert SERVED.
    for r in records:
        if r["external_appointment_id"] == "us-SEED-001":
            r["cancelled"] = True
    await import_service.import_records(service_date=d, source_system=source, records=records)

    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT status FROM appointments WHERE external_appointment_id = 'us-SEED-001'"))).first()
    assert row.status == "SERVED"  # history preserved
