"""Remote functional verification against the deployed HTTPS customer demo.

Reads rotated credentials from CUSTOMER_CREDENTIALS.txt, exercises the full
customer journey + concurrency + RBAC + language + display/report, and writes
PASS/FAIL results to evidence.
"""
import asyncio
import json
import uuid
from pathlib import Path

import httpx

BASE = "https://qms-demo.2.24.0.91.sslip.io"
CREDS_FILE = Path("/root/qms-v1/deploy/demo/CUSTOMER_CREDENTIALS.txt")
OUT = Path("/root/qms-v1/evidence/runs/qms-v1-customer-demo-deployment-001")
OUT.mkdir(parents=True, exist_ok=True)


def read_creds() -> dict:
    creds = {}
    for line in CREDS_FILE.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        u, p = line.split(":", 1)
        creds[u.strip()] = p.strip()
    return creds


async def login(client, u, p):
    r = await client.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    return r.status_code, r.json()


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


async def call_next(client, tok, cid):
    r = await client.post(f"{BASE}/api/cashiers/{cid}/call-next", headers=hdr(tok), timeout=30)
    return cid, r.status_code, r.json()


def main():
    results = []
    creds = read_creds()

    def check(name, cond, detail=""):
        results.append({"test": name, "pass": bool(cond), "detail": detail})
        print(f"{'PASS' if cond else 'FAIL'}: {name} {detail}")

    async def run():
        async with httpx.AsyncClient(timeout=30, verify=True) as c:
            # 1. Login all roles
            tokens = {}
            for role, username in [("admin", "admin"), ("reception", "reception"), ("WIN1", "WIN1"), ("WIN2", "WIN2"), ("WIN3", "WIN3"), ("WIN4", "WIN4")]:
                st, body = await login(c, username, creds[username])
                tokens[role] = body.get("token") if st == 200 else None
                check(f"login {role}", st == 200, f"status={st}")

            # 2. Old default password must be rejected
            st, _ = await login(c, "admin", "admin123")
            check("old seed password rejected", st == 401, f"status={st}")

            # 3. RBAC: reception cannot call-next, cashier cannot check-in
            r = await c.post(f"{BASE}/api/cashiers/1/call-next", headers=hdr(tokens["reception"]))
            check("RBAC: reception cannot call-next", r.status_code == 403, f"status={r.status_code}")
            r = await c.post(f"{BASE}/api/check-ins", headers={**hdr(tokens["WIN1"]), "Idempotency-Key": "rbac-1"}, json={"appointment_ids": [1]})
            check("RBAC: cashier cannot check-in", r.status_code == 403, f"status={r.status_code}")

            # 4. Today's appointments (fictional data)
            r = await c.get(f"{BASE}/api/appointments/today", headers=hdr(tokens["reception"]))
            appts = r.json().get("appointments", [])
            check("today appointments present", len(appts) >= 20, f"count={len(appts)}")

            # 5. Check-ins: earliest (LATE), latest (EARLY), walk-in
            scheduled = [a for a in appts if a["status"] == "SCHEDULED"]
            earliest = min(scheduled, key=lambda a: a["scheduled_at"])
            latest = max(scheduled, key=lambda a: a["scheduled_at"])
            r = await c.post(f"{BASE}/api/check-ins", headers={**hdr(tokens["reception"]), "Idempotency-Key": "d-late"}, json={"appointment_ids": [earliest["id"]]})
            check("check-in LATE", r.status_code == 200 and r.json()["visit"]["visit_type"] == "LATE", r.json().get("visit", {}).get("visit_type"))
            r = await c.post(f"{BASE}/api/check-ins", headers={**hdr(tokens["reception"]), "Idempotency-Key": "d-early"}, json={"appointment_ids": [latest["id"]]})
            check("check-in EARLY", r.status_code == 200 and r.json()["visit"]["visit_type"] == "EARLY", r.json().get("visit", {}).get("visit_type"))
            r = await c.post(f"{BASE}/api/walk-ins", headers={**hdr(tokens["reception"]), "Idempotency-Key": "d-walk"}, json={"name": "Demo Walk-in"})
            check("walk-in", r.status_code == 200, f"ticket={r.json()['ticket']['ticket_number']}")

            # One more check-in so four cashiers each have a waiting ticket.
            mid = sorted(scheduled, key=lambda a: abs(__import__('datetime').datetime.fromisoformat(a['scheduled_at']) - __import__('datetime').datetime.now(__import__('datetime').timezone.utc).replace(tzinfo=None)))[0]
            r = await c.post(f"{BASE}/api/check-ins", headers={**hdr(tokens["reception"]), "Idempotency-Key": "d-mid"}, json={"appointment_ids": [mid["id"]]})
            check("check-in 4th ticket", r.status_code == 200, f"ticket={r.json().get('ticket',{}).get('ticket_number')}")

            # 6. Concurrency: 4 simultaneous call-next
            res = await asyncio.gather(*[call_next(c, tokens[f"WIN{i}"], i) for i in range(1, 5)])
            ids = [r[2]["ticket"]["id"] for r in res if r[1] == 200 and "ticket" in r[2]]
            check("4-way concurrent call-next distinct", len(ids) == 4 and len(set(ids)) == 4, f"ids={ids}")

            # 7. Serve two (start + done)
            served = []
            for cid, code, body in res[:2]:
                tid = body["ticket"]["id"]
                await c.post(f"{BASE}/api/tickets/{tid}/start", headers=hdr(tokens[f"WIN{cid}"]))
                rr = await c.post(f"{BASE}/api/tickets/{tid}/done", headers=hdr(tokens[f"WIN{cid}"]))
                served.append(rr.json()["ticket"]["status"])
            check("serving -> done", all(s == "DONE" for s in served), str(served))

            # 8. Display / calling screen (public, no personal data)
            d = (await c.get(f"{BASE}/api/display/state")).json()
            cs = (await c.get(f"{BASE}/api/calling-screen/state")).json()
            blob = json.dumps(d) + json.dumps(cs)
            check("display no personal data", all(x not in blob.lower() for x in ["guardian", "student", "phone", "booking"]), "")

            # 9. Report
            r = await c.get(f"{BASE}/api/reports/appointments", headers=hdr(tokens["admin"]))
            check("report available", r.status_code == 200 and r.json()["count"] >= 4, f"rows={r.json().get('count')}")

            # 10. Language switching (English default, Arabic persists)
            r = await c.get(f"{BASE}/api/settings/language", params={"scope": "user"}, headers=hdr(tokens["reception"]))
            check("language default en", r.json().get("locale") == "en", r.json().get("locale"))
            await c.put(f"{BASE}/api/settings/language", headers=hdr(tokens["reception"]), json={"scope": "user", "locale": "ar"})
            r = await c.get(f"{BASE}/api/settings/language", params={"scope": "user"}, headers=hdr(tokens["reception"]))
            check("language switch to ar persists", r.json().get("locale") == "ar", r.json().get("locale"))
            await c.put(f"{BASE}/api/settings/language", headers=hdr(tokens["reception"]), json={"scope": "user", "locale": "en"})

    asyncio.run(run())

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    summary = {"passed": passed, "total": total, "results": results}
    (OUT / "remote_functional_tests.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n=== {passed}/{total} passed ===")
    return passed == total


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
