# QMS Customer Demo — Deployment & Operations

## Customer URL

**https://qms-demo.2.24.0.91.sslip.io**

Valid Let's Encrypt TLS (auto-renewing). HTTP redirects to HTTPS.

## Account roles

Passwords are NOT stored in this repository. They live in
`deploy/demo/CUSTOMER_CREDENTIALS.txt` (mode 600, gitignored) and
`deploy/demo/.env` (mode 600, gitignored).

| Username | Role | Screen |
|---|---|---|
| `admin` | ADMIN | check-in, admin, reports, audit, settings |
| `reception` | RECEPTIONIST | check-in, walk-in, settings |
| `WIN1` | CASHIER | cashier station (WINDOW 1) |
| `WIN2` | CASHIER | cashier station (WINDOW 2) |
| `WIN3` | CASHIER | cashier station (WINDOW 3) |
| `WIN4` | CASHIER | cashier station (WINDOW 4) |

Public screens (no login): `/display` (queue overview) and `/calling-screen`
(current ticket + window). Both are read-only and never show personal data.

## Architecture

```
Internet ──> nginx (host, :80/:443, TLS) ──> frontend (127.0.0.1:8081, nginx container)
                                                   ├── /        → static SPA
                                                   ├── /api/*   → backend:8000 (container)
                                                   └── /ws      → backend:8000 (WebSocket, upgrade)
                                                   
backend (127.0.0.1:8101) ──> MySQL 8 (127.0.0.1:3308, isolated `qms_demo` DB)
```

Only nginx (:80/:443) is publicly reachable. MySQL, the API, and the frontend
container are bound to `127.0.0.1` only.

## Start / Stop / Update

```bash
cd /root/qms-v1/deploy/demo

# Start (build + up)
docker compose up -d --build

# Status
docker compose ps

# Logs
docker compose logs -f backend

# Stop
docker compose down

# Stop + wipe the demo DB volume (fresh fictional seed on next start)
docker compose down -v

# Update (rebuild images from the baseline and restart)
docker compose up -d --build

# Rotate credentials (after a fresh seed or on demand)
set -a && . ./.env && set +a
cd /root/qms-v1/backend && . .venv/bin/activate
PYTHONPATH=/root/qms-v1/backend python /root/qms-v1/deploy/demo/rotate_credentials.py
```

## Backup & rollback

**Backup (demo MySQL dump):**

```bash
set -a && . /root/qms-v1/deploy/demo/.env && set +a
docker exec qms-demo-db mysqldump -uqms_demo_user -p"$DEMO_DB_PASSWORD" qms_demo \
  > /root/qms-v1/backups/qms_demo_$(date +%Y%m%d_%H%M%S).sql
```

**Rollback (code):** the certified baseline is tagged `qms-v1-certified-7a70232`
and branched `qms-v1-certified-baseline`. To restore the code:

```bash
cd /root/qms-v1 && git checkout qms-v1-certified-baseline
```

**Rollback (DB):** restore a dump:

```bash
docker exec -i qms-demo-db mysql -uqms_demo_user -p"$DEMO_DB_PASSWORD" qms_demo \
  < /path/to/backup.sql
```

## Firewall / exposed-port verification

The demo exposes **nothing** publicly except nginx :80/:443. Verify:

```bash
ss -ltnp | grep -E ':(3307|3308|8101|8081)\b'   # all must show 127.0.0.1
ss -ltnp | grep -E ':(80|443)\b'                 # nginx only
```

## Notes

- The demo database (`qms_demo`) contains **fictional data only**.
- The real booking database is **not** connected in this deployment.
- `deploy/demo/.env` and `deploy/demo/CUSTOMER_CREDENTIALS.txt` are gitignored
  and never committed.
