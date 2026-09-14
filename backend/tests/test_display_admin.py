"""C14-C16, C18-C22 — display, recovery, reports, RBAC, audit, language."""
import asyncio

import pytest
from sqlalchemy import text

from app.core.db import engine
from tests.conftest import hdr


async def _checkin(client, auth, appointment_id, key):
    r = await client.post(
        "/api/check-ins",
        headers={**hdr(auth["reception"]), "Idempotency-Key": key},
        json={"appointment_ids": [appointment_id]},
    )
    return r


async def _walkin(client, auth, name, key):
    r = await client.post("/api/walk-ins", headers={**hdr(auth["reception"]), "Idempotency-Key": key}, json={"name": name})
    return r


@pytest.mark.asyncio
async def test_c14_live_display(client, auth):
    d0 = (await client.get("/api/display/state")).json()
    before = d0["waiting_count"]

    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    a = [x for x in r.json()["appointments"] if x["status"] == "SCHEDULED"][0]
    ci = await _checkin(client, auth, a["id"], "c14")
    ticket = ci.json()["ticket"]

    d1 = (await client.get("/api/display/state")).json()
    assert d1["waiting_count"] == before + 1

    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    d2 = (await client.get("/api/display/state")).json()
    win1 = [c for c in d2["cashiers"] if c["id"] == 1][0]
    assert win1["current_ticket"] == ticket["ticket_number"]

    await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN1"]))
    await client.post(f"/api/tickets/{ticket['id']}/done", headers=hdr(auth["WIN1"]))
    d3 = (await client.get("/api/display/state")).json()
    win1_after = [c for c in d3["cashiers"] if c["id"] == 1][0]
    assert win1_after["current_ticket"] is None  # Done leaves current-service display


@pytest.mark.asyncio
async def test_c15_reconnect_reconstruction(client, auth):
    # Perform a full cycle, then reconstruct authoritative state from REST.
    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    appts = [x for x in r.json()["appointments"] if x["status"] == "SCHEDULED"]
    for i, a in enumerate(appts[:3]):
        await _checkin(client, auth, a["id"], f"c15-{i}")

    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    await client.post("/api/cashiers/2/call-next", headers=hdr(auth["WIN2"]))

    # Authoritative reconstruction after "missed" events.
    state = (await client.get("/api/display/state")).json()
    cs = (await client.get("/api/calling-screen/state")).json()
    assert state["waiting_count"] == 1  # 3 checked in, 2 called
    assert cs["current"] is not None
    assert cs["current"]["window"] in ("WINDOW 1", "WINDOW 2")


@pytest.mark.asyncio
async def test_c18_complaint_report_timeline(client, auth):
    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    appts = [x for x in r.json()["appointments"] if x["status"] == "SCHEDULED"]
    earliest = min(appts, key=lambda a: a["scheduled_at"])  # -> LATE
    ci = await _checkin(client, auth, earliest["id"], "c18")
    assert ci.json()["visit"]["visit_type"] == "LATE"
    wi = await _walkin(client, auth, "Walkin X", "c18w")
    assert wi.json()["visit"]["visit_type"] == "WALK_IN"

    # Serve both.
    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    t1 = ci.json()["ticket"]
    await client.post(f"/api/tickets/{t1['id']}/start", headers=hdr(auth["WIN1"]))
    await client.post(f"/api/tickets/{t1['id']}/done", headers=hdr(auth["WIN1"]))
    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    t2 = wi.json()["ticket"]
    await client.post(f"/api/tickets/{t2['id']}/start", headers=hdr(auth["WIN1"]))
    await client.post(f"/api/tickets/{t2['id']}/done", headers=hdr(auth["WIN1"]))

    report = (await client.get("/api/reports/appointments", headers=hdr(auth["admin"]))).json()["rows"]
    by_type = {x["visit_type"]: x for x in report}
    assert "LATE" in by_type and "WALK_IN" in by_type
    late = by_type["LATE"]
    assert late["arrival_at"] and late["queue_entered_at"] and late["called_at"] and late["completed_at"]
    assert late["waiting_seconds"] is not None and late["service_seconds"] is not None
    assert late["appointment_ids"]  # scheduled has appointment
    assert not by_type["WALK_IN"]["appointment_ids"]  # walk-in has none


@pytest.mark.asyncio
async def test_c19_rbac_and_privacy(client, auth):
    # Cashier cannot check in.
    r = await client.post("/api/check-ins", headers={**hdr(auth["WIN1"]), "Idempotency-Key": "c19"}, json={"appointment_ids": [1]})
    assert r.status_code == 403
    # Receptionist cannot call next.
    r = await client.post("/api/cashiers/1/call-next", headers=hdr(auth["reception"]))
    assert r.status_code == 403
    # Unauthenticated cannot reach staff endpoints.
    r = await client.get("/api/queue/waiting")
    assert r.status_code == 401

    # Public display/calling state contains no names.
    display = (await client.get("/api/display/state")).json()
    calling = (await client.get("/api/calling-screen/state")).json()
    import json

    blob = json.dumps(display) + json.dumps(calling)
    for forbidden in ["guardian", "student", "phone", "booking", "appointment"]:
        assert forbidden.lower() not in blob.lower()


@pytest.mark.asyncio
async def test_c20_audit_integrity(client, auth):
    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    a = [x for x in r.json()["appointments"] if x["status"] == "SCHEDULED"][0]
    ci = await _checkin(client, auth, a["id"], "c20")
    ticket = ci.json()["ticket"]
    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN1"]))
    await client.post(f"/api/tickets/{ticket['id']}/done", headers=hdr(auth["WIN1"]))

    audit = (await client.get("/api/audit", headers=hdr(auth["admin"]), params={"entity_id": ticket["id"]})).json()["audit"]
    assert len(audit) >= 4  # checked_in, called, serving, completed
    for ev in audit:
        assert ev["occurred_at"] is not None
        assert ev["correlation_id"]
        assert ev["action"]
        assert ev["entity_type"] == "ticket"
    # The completed event records a from_state/to_state transition and an actor.
    completed = [e for e in audit if e["action"] == "ticket.completed"][0]
    assert completed["from_state"] == "SERVING" and completed["to_state"] == "DONE"
    assert completed["actor_user_id"] is not None


@pytest.mark.asyncio
async def test_c21_calling_screen(client, auth):
    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    appts = [x for x in r.json()["appointments"] if x["status"] == "SCHEDULED"]
    await _checkin(client, auth, appts[0]["id"], "c21a")
    await _checkin(client, auth, appts[1]["id"], "c21b")

    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    cs = (await client.get("/api/calling-screen/state")).json()
    assert cs["current"]["window"] == "WINDOW 1"
    assert cs["current"]["ticket_number"] >= 1
    assert len(cs["recent"]) >= 1
    assert cs["current"]["ticket_number"] == cs["recent"][0]["ticket_number"]


@pytest.mark.asyncio
async def test_c22_language_switching(client, auth):
    # English default.
    r = await client.get("/api/settings/language", params={"scope": "user"}, headers=hdr(auth["reception"]))
    assert r.json()["locale"] == "en"

    # Switch to Arabic; persists.
    r = await client.put("/api/settings/language", headers=hdr(auth["reception"]), json={"scope": "user", "locale": "ar"})
    assert r.json()["locale"] == "ar"
    r = await client.get("/api/settings/language", params={"scope": "user"}, headers=hdr(auth["reception"]))
    assert r.json()["locale"] == "ar"

    # Back to English.
    await client.put("/api/settings/language", headers=hdr(auth["reception"]), json={"scope": "user", "locale": "en"})

    # Public display locale: default en, admin can set to ar.
    r = await client.get("/api/settings/language", params={"scope": "calling_screen"})
    assert r.json()["locale"] == "en"
    r = await client.put("/api/settings/language", headers=hdr(auth["admin"]), json={"scope": "calling_screen", "locale": "ar"})
    assert r.status_code == 200
    r = await client.get("/api/settings/language", params={"scope": "calling_screen"})
    assert r.json()["locale"] == "ar"
