"""C03-C07 — reception vertical slice."""
import pytest

from app.core.time import today_local
from app.services import query_service


async def _first_scheduled(client, auth):
    r = await client.get("/api/appointments/today", headers={"Authorization": f"Bearer {auth['reception']}"})
    appts = r.json()["appointments"]
    return [a for a in appts if a["status"] == "SCHEDULED"][0]


@pytest.mark.asyncio
async def test_c03_normal_checkin(client, auth):
    a = await _first_scheduled(client, auth)
    r = await client.post(
        "/api/check-ins",
        headers={"Authorization": f"Bearer {auth['reception']}", "Idempotency-Key": "c03"},
        json={"guardian_id": a["guardian_id"], "appointment_ids": [a["id"]]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ticket"]["status"] == "WAITING"
    assert body["ticket"]["ticket_number"] >= 1

    waiting = (await client.get("/api/queue/waiting", headers={"Authorization": f"Bearer {auth['reception']}"})).json()["waiting"]
    assert any(w["id"] == body["ticket"]["id"] for w in waiting)


@pytest.mark.asyncio
async def test_c04_duplicate_checkin_rejected(client, auth):
    a = await _first_scheduled(client, auth)
    headers = {"Authorization": f"Bearer {auth['reception']}"}
    r1 = await client.post("/api/check-ins", headers={**headers, "Idempotency-Key": "c04a"}, json={"appointment_ids": [a["id"]]})
    assert r1.status_code == 200
    # Replay same key -> original result (idempotent).
    r2 = await client.post("/api/check-ins", headers={**headers, "Idempotency-Key": "c04a"}, json={"appointment_ids": [a["id"]]})
    assert r2.status_code == 200
    assert r2.json()["ticket"]["id"] == r1.json()["ticket"]["id"]
    # Different key -> rejected as duplicate.
    r3 = await client.post("/api/check-ins", headers={**headers, "Idempotency-Key": "c04b"}, json={"appointment_ids": [a["id"]]})
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "DUPLICATE_CHECK_IN"


@pytest.mark.asyncio
async def test_c05_multi_appointment(client, auth):
    # Find a guardian with 2+ same-day appointments.
    r = await client.get("/api/appointments/today", headers={"Authorization": f"Bearer {auth['reception']}"})
    appts = [a for a in r.json()["appointments"] if a["status"] == "SCHEDULED"]
    by_g = {}
    for a in appts:
        by_g.setdefault(a["guardian_id"], []).append(a)
    guardian_id, group = next((g, v) for g, v in by_g.items() if len(v) >= 2)

    headers = {"Authorization": f"Bearer {auth['reception']}"}
    # Guardian view shows all same-day appointments.
    gv = await client.get(f"/api/guardians/{guardian_id}/appointments/today", headers=headers)
    assert len(gv.json()["appointments"]) >= 2

    # Select only the first two.
    selected = [group[0]["id"], group[1]["id"]]
    ci = await client.post("/api/check-ins", headers={**headers, "Idempotency-Key": "c05"}, json={"appointment_ids": selected})
    assert ci.status_code == 200
    body = ci.json()
    assert body["visit"]["multi_appointment"] is True
    assert len(body["appointments"]) == 2

    # Unselected future appointment (if any beyond 2) remains SCHEDULED.
    rest = [a for a in group if a["id"] not in selected]
    if rest:
        after = await client.get(f"/api/guardians/{guardian_id}/appointments/today", headers=headers)
        statuses = {a["id"]: a["status"] for a in after.json()["appointments"]}
        assert statuses[rest[0]["id"]] == "SCHEDULED"


@pytest.mark.asyncio
async def test_c06_early_arrival(client, auth):
    # The seed's most-future appointment arrives early (now is before its window).
    r = await client.get("/api/appointments/today", headers={"Authorization": f"Bearer {auth['reception']}"})
    appts = [a for a in r.json()["appointments"] if a["status"] == "SCHEDULED"]
    latest = max(appts, key=lambda a: a["scheduled_at"])
    ci = await client.post(
        "/api/check-ins",
        headers={"Authorization": f"Bearer {auth['reception']}", "Idempotency-Key": "c06"},
        json={"appointment_ids": [latest["id"]]},
    )
    assert ci.status_code == 200
    assert ci.json()["visit"]["visit_type"] == "EARLY"


@pytest.mark.asyncio
async def test_c06_late_arrival(client, auth):
    r = await client.get("/api/appointments/today", headers={"Authorization": f"Bearer {auth['reception']}"})
    appts = [a for a in r.json()["appointments"] if a["status"] == "SCHEDULED"]
    earliest = min(appts, key=lambda a: a["scheduled_at"])
    ci = await client.post(
        "/api/check-ins",
        headers={"Authorization": f"Bearer {auth['reception']}", "Idempotency-Key": "c06late"},
        json={"appointment_ids": [earliest["id"]]},
    )
    assert ci.status_code == 200
    assert ci.json()["visit"]["visit_type"] == "LATE"


@pytest.mark.asyncio
async def test_c07_walkin(client, auth):
    headers = {"Authorization": f"Bearer {auth['reception']}"}
    r = await client.post(
        "/api/walk-ins",
        headers={**headers, "Idempotency-Key": "c07"},
        json={"name": "Walkin Guardian", "phone": "0550000000"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["visit"]["visit_type"] == "WALK_IN"
    assert body["appointments"] == []

    waiting = (await client.get("/api/queue/waiting", headers=headers)).json()["waiting"]
    assert any(w["id"] == body["ticket"]["id"] for w in waiting)

    # Report distinguishes walk-in (no appointment).
    report = (await client.get("/api/reports/appointments", headers={"Authorization": f"Bearer {auth['admin']}"})).json()
    row = [x for x in report["rows"] if x["ticket_id"] == body["ticket"]["id"]][0]
    assert row["visit_type"] == "WALK_IN"
    assert not row["appointment_ids"]
