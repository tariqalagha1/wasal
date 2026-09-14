# Queue Management System — QMS V1

Production-ready V1 queue management system for one reception/check-in station,
four cashier stations, one queue overview display, one separate public calling
screen, and one admin/report interface.

**Canonical loop:** `daily import → identify guardian → select/cover appointments →
check-in / walk-in → Waiting → atomic Call Next → Called → Serving → Done →
live display → audit/report`

## Stack

- Backend: Python **FastAPI** (async SQLAlchemy + asyncmy)
- Frontend: **React + TypeScript + Vite**
- Database: **MySQL 8** (source of truth)
- Realtime: **WebSocket** (notification-only)
- Interfaces: English default, optional Arabic (RTL) in Settings
- Deployment: **Docker Compose**

## Quick start (Docker Compose)

```bash
cd infra
cp ../.env.example ../.env   # edit JWT_SECRET
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8100 (health: `/health`)
- MySQL: localhost:3307 (db `qms`, user `qms_user`)

On first boot the backend applies migrations and seeds:
- users, 4 cashier stations, and today's appointments (idempotent import).

## Local development (no Docker for app)

```bash
# 1. MySQL 8 (Docker)
docker run -d --name qms-mysql -p 3307:3306 \
  -e MYSQL_ROOT_PASSWORD=rootpass -e MYSQL_DATABASE=qms \
  -e MYSQL_USER=qms_user -e MYSQL_PASSWORD=qms_pass mysql:8.0

# 2. Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8100

# 3. Frontend
cd ../frontend
npm install
npm run dev   # http://localhost:5173 (proxies /api and /ws to :8100)
```

## Seed credentials

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Receptionist | `reception` | `reception123` |
| Cashier (window 1) | `WIN1` | `cashier123` |
| Cashier (window 2) | `WIN2` | `cashier123` |
| Cashier (window 3) | `WIN3` | `cashier123` |
| Cashier (window 4) | `WIN4` | `cashier123` |

A CASHIER user's username equals the station `code`.

## Screens / routes

| Route | Screen | Access |
|---|---|---|
| `/login` | Login | staff |
| `/check-in` | Reception / check-in | Receptionist, Admin |
| `/cashier/:cashierId` | Cashier station | Cashier, Admin |
| `/display` | Queue overview | public |
| `/calling-screen` | Current ticket + window (large text) | public |
| `/admin` | Users, cashiers, import status | Admin |
| `/reports` | Appointment/service report | Admin |
| `/audit` | Audit history | Admin |
| `/settings` | Language (English/العربية) | staff |

## Tests

```bash
cd backend
. .venv/bin/activate
python -m pytest -q
```

Tests run against a real MySQL 8 instance (`qms_test` database). They cover the
full acceptance matrix (C01–C22): import idempotency, check-in/walk-in,
multi-appointment, early/late classification, four-way concurrent Call Next,
collision stress, ownership, lifecycle, cashier-busy, completion coverage,
display/reconnect, reports, RBAC/privacy, audit integrity, calling screen, and
language switching.

## Operational decisions (documented)

- **Timezone:** all timestamps stored as naive UTC; operational dates computed
  in `Asia/Riyadh` (configurable via `APP_TIMEZONE`).
- **Cashier mapping:** a CASHIER user's username equals the station `code`.
- **Cancellation:** cancelling a WAITING/CALLED ticket reverts its linked
  CHECKED_IN appointments to SCHEDULED (service never happened); full history
  is preserved in `audit_events`.
- **Recall:** `called_at` is updated on recall (the calling screen re-highlights
  the same pair); the original call is preserved in the audit log.

## V1 exclusions (deferred)

Redis/multi-instance broadcasting, Celery, notifications (SMS/email),
kiosks/QR, mobile apps, multi-tenancy, advanced analytics, AI, Kubernetes.
