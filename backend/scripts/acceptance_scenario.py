"""Blind acceptance scenario: mixed check-ins + walk-in -> 4 cashiers -> display -> report.

Writes evidence under evidence/runs/qms-v1-build-001/.
"""
import asyncio
import json
import uuid
from pathlib import Path

import httpx

BASE = "http://localhost:8100"
OUT = Path("/root/qms-v1/evidence/runs/qms-v1-build-001")
OUT.mkdir(parents=True, exist_ok=True)


def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    r.raise_for_status()
    return r.json()["token"]


def h(token):
    return {"Authorization": f"Bearer {token}"}


def k():
    return uuid.uuid4().hex


async def call_next_async(token, cid):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/api/cashiers/{cid}/call-next", headers=h(token), timeout=30)
        return cid, r.status_code, r.json()


async def main():
    admin = login("admin", "admin123")
    rec = login("reception", "reception123")
    win = {i: login(f"WIN{i}", "cashier123") for i in range(1, 5)}

    log = []

    # 0. reset operational state (via a fresh import + check current queue is empty)
    r = httpx.get(f"{BASE}/api/appointments/today", headers=h(rec))
    appts = [a for a in r.json()["appointments"] if a["status"] == "SCHEDULED"]
    log.append(f"today appointments (scheduled): {len(appts)}")

    by_guardian = {}
    for a in appts:
        by_guardian.setdefault(a["guardian_id"], []).append(a)

    # 1. check-ins: earliest (LATE), latest (EARLY), a multi-appointment guardian, walk-in
    earliest = min(appts, key=lambda a: a["scheduled_at"])
    latest = max(appts, key=lambda a: a["scheduled_at"])
    # Multi-appointment guardian: pick a guardian with >=2 appointments that is
    # NOT the owner of the earliest/latest appointment (to avoid overlap).
    multi_guardian = next(
        (g, v) for g, v in sorted(by_guardian.items())
        if len(v) >= 2 and g != earliest["guardian_id"] and g != latest["guardian_id"]
    )

    def checkin(ids, key):
        r = httpx.post(f"{BASE}/api/check-ins", headers={**h(rec), "Idempotency-Key": key}, json={"appointment_ids": ids})
        return r.status_code, r.json()

    st, late = checkin([earliest["id"]], k()); log.append(f"check-in LATE: {st} {late['visit']['visit_type']} ticket={late['ticket']['ticket_number']}")
    st, early = checkin([latest["id"]], k()); log.append(f"check-in EARLY: {st} {early['visit']['visit_type']} ticket={early['ticket']['ticket_number']}")
    st, multi = checkin([multi_guardian[1][0]["id"], multi_guardian[1][1]["id"]], k()); log.append(f"check-in MULTI: {st} multi={multi['visit']['multi_appointment']} ticket={multi['ticket']['ticket_number']}")
    # a scheduled/on-time check-in (an appointment near now)
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    near_now = min(appts, key=lambda a: abs(dt.datetime.fromisoformat(a['scheduled_at']) - now))
    if near_now["id"] not in (earliest["id"], latest["id"], multi_guardian[1][0]["id"], multi_guardian[1][1]["id"]):
        st, sch = checkin([near_now["id"]], k()); log.append(f"check-in SCHEDULED: {st} {sch['visit']['visit_type']} ticket={sch['ticket']['ticket_number']}")
    else:
        sch = None
    # walk-in
    rw = httpx.post(f"{BASE}/api/walk-ins", headers={**h(rec), "Idempotency-Key": k()}, json={"name": "Walkin Guardian", "phone": "0550000000"})
    walk = (rw.status_code, rw.json()); log.append(f"walk-in: {walk[0]} ticket={walk[1]['ticket']['ticket_number']}")

    # 2. four concurrent call-next
    results = await asyncio.gather(*[call_next_async(win[i], i) for i in range(1, 5)])
    assigned = []
    for cid, code, body in results:
        if code == 200 and "ticket" in body:
            t = body["ticket"]
            assigned.append({"cashier": cid, "ticket_id": t["id"], "ticket_number": t["ticket_number"]})
            log.append(f"call-next WIN{cid}: ticket={t['ticket_number']}")
        else:
            log.append(f"call-next WIN{cid}: {code} {body}")
    distinct = len({a["ticket_id"] for a in assigned})
    log.append(f"CONCURRENT CALL NEXT: {len(assigned)} tickets, {distinct} distinct")

    # 3. serve two of them (start + done)
    for a in assigned[:2]:
        httpx.post(f"{BASE}/api/tickets/{a['ticket_id']}/start", headers=h(win[a["cashier"]]))
        r = httpx.post(f"{BASE}/api/tickets/{a['ticket_id']}/done", headers=h(win[a["cashier"]]))
        log.append(f"serve ticket {a['ticket_number']}: done status={r.json()['ticket']['status']}")

    # 4. display + calling screen + report
    display = httpx.get(f"{BASE}/api/display/state").json()
    calling = httpx.get(f"{BASE}/api/calling-screen/state").json()
    report = httpx.get(f"{BASE}/api/reports/appointments", headers=h(admin)).json()
    log.append(f"display: waiting={display['waiting_count']} cashiers={len(display['cashiers'])}")
    log.append(f"calling-screen current: {calling['current']}")
    log.append(f"report rows: {report['count']}")

    # Write evidence files.
    (OUT / "scenario.log").write_text("\n".join(log), encoding="utf-8")
    (OUT / "display_state.json").write_text(json.dumps(display, indent=2, default=str), encoding="utf-8")
    (OUT / "calling_screen_state.json").write_text(json.dumps(calling, indent=2, default=str), encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "concurrent_assignments.json").write_text(json.dumps({"assigned": assigned, "distinct": distinct}, indent=2), encoding="utf-8")

    print("\n".join(log))
    print(f"\nEvidence written to {OUT}")


asyncio.run(main())
