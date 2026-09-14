"""C08-C13, C17 — cashier lifecycle, concurrency, ownership."""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.db import engine
from app.models.models import Cashier, User
from app.services import transition_service
from tests.conftest import hdr, tokens


async def _stations() -> dict[int, Cashier]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, code, display_name, active, sort_order FROM cashiers ORDER BY id"))).fetchall()
    return {r.id: Cashier(id=r.id, code=r.code, display_name=r.display_name, active=r.active, sort_order=r.sort_order) for r in rows}


async def _checkin_many(client, auth, n):
    import uuid

    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    appts = [a for a in r.json()["appointments"] if a["status"] == "SCHEDULED"]
    ids = []
    for i, a in enumerate(appts[:n]):
        rr = await client.post(
            "/api/check-ins",
            headers={**hdr(auth["reception"]), "Idempotency-Key": f"m-{i}-{uuid.uuid4().hex}"},
            json={"appointment_ids": [a["id"]]},
        )
        assert rr.status_code == 200, rr.text
        ids.append(rr.json()["ticket"]["id"])
    return ids


@pytest.mark.asyncio
async def test_c08_c09_concurrent_call_next_no_collision(client, auth):
    # Check in 12 to have plenty of waiting tickets.
    await _checkin_many(client, auth, 12)

    stations = await _stations()
    actor = SimpleNamespace(id=1, role="ADMIN", username="admin")

    # Round 1: four simultaneous cashiers -> four distinct oldest tickets.
    results = await asyncio.gather(
        *[transition_service.call_next(station=stations[i], actor=actor) for i in range(1, 5)]
    )
    codes = [r[0] for r in results]
    tickets = [r[1]["ticket"] for r in results if r[1].get("ticket")]
    assert codes == [200, 200, 200, 200]
    assert len({t["id"] for t in tickets}) == 4, "collision: ticket assigned twice"

    # C09: repeated simultaneous calls never assign the same ticket twice.
    # Cashiers must release their active ticket before calling again.
    for t in tickets:
        await transition_service.start_serving(ticket_id=t["id"], station=stations[t["cashier_id"]], actor=actor)
        await transition_service.complete(ticket_id=t["id"], station=stations[t["cashier_id"]], actor=actor)

    seen: set[int] = set()
    for _ in range(3):
        results = await asyncio.gather(
            *[transition_service.call_next(station=stations[i], actor=actor) for i in range(1, 5)]
        )
        for r in results:
            t = r[1].get("ticket")
            if t:
                assert t["id"] not in seen, "COLLISION across rounds"
                seen.add(t["id"])
                await transition_service.start_serving(ticket_id=t["id"], station=stations[t["cashier_id"]], actor=actor)
                await transition_service.complete(ticket_id=t["id"], station=stations[t["cashier_id"]], actor=actor)
    assert len(seen) >= 8


@pytest.mark.asyncio
async def test_c10_ownership(client, auth):
    ids = await _checkin_many(client, auth, 2)
    # WIN1 calls next -> assigned to WIN1.
    r = await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    assert r.status_code == 200
    ticket = r.json()["ticket"]
    assert ticket["cashier_id"] == 1

    # WIN2 cannot start WIN1's ticket.
    r2 = await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN2"]))
    assert r2.status_code == 403

    # WIN1 can start its own ticket.
    r3 = await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN1"]))
    assert r3.status_code == 200
    assert r3.json()["ticket"]["status"] == "SERVING"


@pytest.mark.asyncio
async def test_c11_lifecycle(client, auth):
    await _checkin_many(client, auth, 1)
    r = await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    ticket = r.json()["ticket"]
    assert ticket["status"] == "CALLED"

    # Called -> Done directly must fail (must go through Serving).
    d = await client.post(f"/api/tickets/{ticket['id']}/done", headers=hdr(auth["WIN1"]))
    assert d.status_code == 409

    # Called -> Serving -> Done succeeds.
    s = await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN1"]))
    assert s.status_code == 200
    dn = await client.post(f"/api/tickets/{ticket['id']}/done", headers=hdr(auth["WIN1"]))
    assert dn.status_code == 200
    assert dn.json()["ticket"]["status"] == "DONE"

    # Done is terminal.
    again = await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN1"]))
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_c12_cashier_busy(client, auth):
    await _checkin_many(client, auth, 3)
    r1 = await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    assert r1.status_code == 200
    r2 = await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "CASHIER_BUSY"


@pytest.mark.asyncio
async def test_c13_completion_coverage(client, auth):
    # Guardian with two appointments; select only one.
    r = await client.get("/api/appointments/today", headers=hdr(auth["reception"]))
    appts = [a for a in r.json()["appointments"] if a["status"] == "SCHEDULED"]
    by_g = {}
    for a in appts:
        by_g.setdefault(a["guardian_id"], []).append(a)
    gid, group = next((g, v) for g, v in by_g.items() if len(v) >= 2)
    selected = group[0]
    unselected = group[1]

    ci = await client.post(
        "/api/check-ins",
        headers={**hdr(auth["reception"]), "Idempotency-Key": "c13"},
        json={"appointment_ids": [selected["id"]]},
    )
    ticket = ci.json()["ticket"]
    await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    await client.post(f"/api/tickets/{ticket['id']}/start", headers=hdr(auth["WIN1"]))
    dn = await client.post(f"/api/tickets/{ticket['id']}/done", headers=hdr(auth["WIN1"]))
    assert dn.status_code == 200
    assert dn.json()["served_appointments"] == [selected["id"]]

    async with engine.connect() as conn:
        sel = (await conn.execute(text("SELECT status FROM appointments WHERE id = :i"), {"i": selected["id"]})).scalar_one()
        uns = (await conn.execute(text("SELECT status FROM appointments WHERE id = :i"), {"i": unselected["id"]})).scalar_one()
        tk = (await conn.execute(text("SELECT cashier_id, called_at, service_started_at, completed_at FROM queue_tickets WHERE id = :i"), {"i": ticket["id"]})).first()
    assert sel == "SERVED"
    assert uns == "SCHEDULED"
    assert tk.cashier_id == 1
    assert tk.called_at is not None and tk.service_started_at is not None and tk.completed_at is not None


@pytest.mark.asyncio
async def test_c17_noshow_return_to_queue(client, auth):
    await _checkin_many(client, auth, 2)
    r = await client.post("/api/cashiers/1/call-next", headers=hdr(auth["WIN1"]))
    ticket = r.json()["ticket"]
    assert ticket["status"] == "CALLED"

    ns = await client.post(f"/api/tickets/{ticket['id']}/no-show", headers=hdr(auth["WIN1"]), json={"reason": "left"})
    assert ns.status_code == 200
    assert ns.json()["ticket"]["status"] == "NO_SHOW"

    rt = await client.post(f"/api/tickets/{ticket['id']}/return-to-queue", headers=hdr(auth["reception"]))
    assert rt.status_code == 200
    assert rt.json()["ticket"]["status"] == "WAITING"

    # Audited: no_show + returned_to_queue events present.
    audit = (await client.get("/api/audit", headers=hdr(auth["admin"]), params={"entity_id": ticket["id"]})).json()["audit"]
    actions = {a["action"] for a in audit}
    assert "ticket.no_show" in actions and "ticket.returned_to_queue" in actions
