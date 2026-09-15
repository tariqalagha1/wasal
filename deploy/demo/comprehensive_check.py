"""Comprehensive functional check of the deployed demo — all cashiers, recall,
no-show/return, repeated calling, start serving, and admin screen.
"""
import asyncio
import json
import uuid
from pathlib import Path

import httpx

BASE = "https://qms-demo.2.24.0.91.sslip.io"
CREDS = Path("/root/qms-v1/deploy/demo/CUSTOMER_CREDENTIALS.txt")
OUT = Path("/root/qms-v1/evidence/runs/qms-v1-customer-demo-deployment-001")
OUT.mkdir(parents=True, exist_ok=True)

creds = {}
for line in CREDS.read_text().splitlines():
    line = line.split("#")[0].strip()
    if line:
        u, p = line.split(":", 1)
        creds[u.strip()] = p.strip()


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        print(f"{'PASS' if cond else 'FAIL'}: {name} {detail}")

    async def run():
        async with httpx.AsyncClient(timeout=30, verify=True) as c:
            async def login(u, p):
                r = await c.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
                return r.json()["token"] if r.status_code == 200 else None

            rec = await login("reception", creds["reception"])
            adm = await login("admin", creds["admin"])
            win = {i: await login(f"WIN{i}", creds[f"WIN{i}"]) for i in range(1, 5)}
            check("all 6 logins", all([rec, adm] + [win[i] for i in range(1, 5)]))

            # --- Reception: check in 5 + walk-in -> 6 waiting tickets ---
            appts = (await c.get(f"{BASE}/api/appointments/today", headers=h(rec))).json()["appointments"]
            sched = [a for a in appts if a["status"] == "SCHEDULED"]
            for i, a in enumerate(sched[:5]):
                r = await c.post(f"{BASE}/api/check-ins", headers={**h(rec), "Idempotency-Key": f"c{i}"}, json={"appointment_ids": [a["id"]]})
                check(f"check-in #{i+1}", r.status_code == 200, f"ticket={r.json().get('ticket',{}).get('ticket_number')}")
            r = await c.post(f"{BASE}/api/walk-ins", headers={**h(rec), "Idempotency-Key": "w"}, json={"name": "Walkin"})
            check("walk-in", r.status_code == 200)

            q = (await c.get(f"{BASE}/api/queue/waiting", headers=h(rec))).json()["waiting"]
            check("6 waiting tickets", len(q) == 6, f"count={len(q)}")

            # --- Different cashiers + full lifecycle ---
            async def call(cid):
                r = await c.post(f"{BASE}/api/cashiers/{cid}/call-next", headers=h(win[cid]))
                return r.status_code, r.json()

            # WIN1: call -> start -> done
            st, b = await call(1); t1 = b["ticket"]
            check("WIN1 call-next", st == 200, f"ticket={t1['ticket_number']}")
            check("WIN1 start serving", (await c.post(f"{BASE}/api/tickets/{t1['id']}/start", headers=h(win[1]))).status_code == 200)
            check("WIN1 done", (await c.post(f"{BASE}/api/tickets/{t1['id']}/done", headers=h(win[1]))).status_code == 200)

            # WIN2: call -> recall -> start -> done
            st, b = await call(2); t2 = b["ticket"]
            check("WIN2 call-next", st == 200, f"ticket={t2['ticket_number']}")
            rr = await c.post(f"{BASE}/api/tickets/{t2['id']}/recall", headers=h(win[2]))
            check("WIN2 recall", rr.status_code == 200 and rr.json()["ticket"]["recall_count"] == 1, f"recall_count={rr.json()['ticket']['recall_count']}")
            check("WIN2 start after recall", (await c.post(f"{BASE}/api/tickets/{t2['id']}/start", headers=h(win[2]))).status_code == 200)
            check("WIN2 done", (await c.post(f"{BASE}/api/tickets/{t2['id']}/done", headers=h(win[2]))).status_code == 200)

            # WIN3: call -> no-show -> return to queue
            st, b = await call(3); t3 = b["ticket"]
            check("WIN3 call-next", st == 200, f"ticket={t3['ticket_number']}")
            check("WIN3 no-show", (await c.post(f"{BASE}/api/tickets/{t3['id']}/no-show", headers=h(win[3]), json={})).status_code == 200)
            check("return-to-queue (reception)", (await c.post(f"{BASE}/api/tickets/{t3['id']}/return-to-queue", headers=h(rec))).status_code == 200)
            # returned ticket should be back in WAITING
            q = (await c.get(f"{BASE}/api/queue/waiting", headers=h(rec))).json()["waiting"]
            check("returned ticket back in queue", any(x["id"] == t3["id"] for x in q))

            # WIN4: call -> start -> done
            st, b = await call(4); t4 = b["ticket"]
            check("WIN4 call-next", st == 200, f"ticket={t4['ticket_number']}")
            check("WIN4 start serving", (await c.post(f"{BASE}/api/tickets/{t4['id']}/start", headers=h(win[4]))).status_code == 200)
            check("WIN4 done", (await c.post(f"{BASE}/api/tickets/{t4['id']}/done", headers=h(win[4]))).status_code == 200)

            # --- Ownership: WIN2 cannot touch WIN1's (now DONE) ticket, and vice versa ---
            # (already served; test a fresh cross-cashier attempt)
            # WIN1 calls next again (repeated calling)
            st, b = await call(1); t5 = b["ticket"]
            check("WIN1 call-next again (repeated)", st == 200, f"ticket={t5['ticket_number']}")
            # WIN2 tries to start WIN1's ticket -> 403
            r = await c.post(f"{BASE}/api/tickets/{t5['id']}/start", headers=h(win[2]))
            check("ownership: WIN2 cannot start WIN1 ticket", r.status_code == 403, f"status={r.status_code}")
            check("WIN1 completes", (await c.post(f"{BASE}/api/tickets/{t5['id']}/start", headers=h(win[1]))).status_code == 200)

            # --- Admin screen data ---
            r = await c.get(f"{BASE}/api/users", headers=h(adm))
            check("admin: list users", r.status_code == 200 and len(r.json()["users"]) == 6, f"users={len(r.json()['users'])}")
            r = await c.get(f"{BASE}/api/admin/cashiers", headers=h(adm))
            check("admin: list cashiers", r.status_code == 200 and len(r.json()["cashiers"]) == 4, f"cashiers={len(r.json()['cashiers'])}")
            r = await c.get(f"{BASE}/api/reports/appointments", headers=h(adm))
            check("admin: report", r.status_code == 200 and r.json()["count"] >= 6, f"rows={r.json()['count']}")
            r = await c.get(f"{BASE}/api/audit", headers=h(adm))
            check("admin: audit log", r.status_code == 200 and len(r.json()["audit"]) >= 10, f"events={len(r.json()['audit'])}")
            r = await c.get(f"{BASE}/api/imports", headers=h(adm))
            check("admin: import history", r.status_code == 200, f"runs={len(r.json()['imports'])}")
            # RBAC: reception cannot see admin endpoints
            r = await c.get(f"{BASE}/api/users", headers=h(rec))
            check("RBAC: reception blocked from /users", r.status_code == 403)

    asyncio.run(run())
    passed = sum(1 for _, ok, _ in results if ok)
    (OUT / "comprehensive_functional_check.json").write_text(json.dumps({"passed": passed, "total": len(results), "results": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results]}, indent=2), encoding="utf-8")
    print(f"\n=== {passed}/{len(results)} passed ===")
    return passed == len(results)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
