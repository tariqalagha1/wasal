"""Idempotent seed for users, cashiers, settings, and today's appointments.

Run at startup when the database is empty. Appointment times are generated
relative to now so the acceptance scenarios produce EARLY / SCHEDULED / LATE
classifications and multi-appointment guardians.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import text

from app.core.security import hash_password
from app.core.time import now_utc, today_local
from app.services import import_service

SEED_USERS = [
    ("admin", "admin123", "ADMIN", "en"),
    ("reception", "reception123", "RECEPTIONIST", "en"),
    ("WIN1", "cashier123", "CASHIER", "en"),
    ("WIN2", "cashier123", "CASHIER", "en"),
    ("WIN3", "cashier123", "CASHIER", "en"),
    ("WIN4", "cashier123", "CASHIER", "en"),
]

SEED_CASHIERS = [
    ("WIN1", "WINDOW 1", 1),
    ("WIN2", "WINDOW 2", 2),
    ("WIN3", "WINDOW 3", 3),
    ("WIN4", "WINDOW 4", 4),
]


async def seed_if_empty() -> dict:
    from app.core.db import engine

    result: dict = {"seeded": False, "details": []}

    async with engine.connect() as conn:
        async with conn.begin():
            user_count = (await conn.execute(text("SELECT COUNT(*) FROM users"))).scalar_one()
            if user_count > 0:
                return result

            for username, password, role, locale in SEED_USERS:
                await conn.execute(
                    text("INSERT INTO users (username, password_hash, role, preferred_locale, active) VALUES (:u, :p, :r, :l, TRUE)"),
                    {"u": username, "p": hash_password(password), "r": role, "l": locale},
                )
            result["details"].append("users created")

            for code, display_name, sort_order in SEED_CASHIERS:
                await conn.execute(
                    text("INSERT INTO cashiers (code, display_name, active, sort_order) VALUES (:c, :d, TRUE, :s)"),
                    {"c": code, "d": display_name, "s": sort_order},
                )
            result["details"].append("cashiers created")

            for key, value in (("public_display_locale", "en"), ("calling_screen_locale", "en")):
                await conn.execute(
                    text(
                        "INSERT INTO system_settings (setting_key, setting_value, updated_at) VALUES (:k, :v, :now) AS new "
                        "ON DUPLICATE KEY UPDATE setting_value = new.setting_value, updated_at = new.updated_at"
                    ),
                    {"k": key, "v": json.dumps({"locale": value}), "now": now_utc()},
                )
            result["details"].append("settings created")

        # Import today's appointments (twice to prove idempotency).
        service_date = today_local()
        records = _seed_records(service_date)
        first = await import_service.import_records(service_date=service_date, source_system="seed", records=records)
        second = await import_service.import_records(service_date=service_date, source_system="seed", records=records)
        result["details"].append(f"import 1: inserted={first['inserted']} updated={first['updated']}")
        result["details"].append(f"import 2 (idempotent): inserted={second['inserted']} updated={second['updated']}")

        result["seeded"] = True

    return result


def _seed_records(service_date) -> list[dict]:
    now = now_utc()
    guardians = [
        ("G-001", "Abdullah Al-Otaibi", "0500000001"),
        ("G-002", "Khalid Al-Harbi", "0500000002"),
        ("G-003", "Sara Al-Qahtani", "0500000003"),
        ("G-004", "Fatimah Al-Shammari", "0500000004"),
        ("G-005", "Mansour Al-Dossari", "0500000005"),
        ("G-006", "Noura Al-Ghamdi", "0500000006"),
        ("G-007", "Omar Al-Zahrani", "0500000007"),
        ("G-008", "Layla Al-Anazi", "0500000008"),
    ]
    # Offset spread: past (LATE), near-now (SCHEDULED), future (EARLY).
    offsets = [
        -90, -75, -60, -45, -30, -20, -10, -5,   # late
        -3, 0, 3, 5, 8,                          # scheduled/on-time
        10, 12, 15, 20, 30, 45, 60, 75, 90,      # early
    ]
    records = []
    for i, off in enumerate(offsets):
        g = guardians[i % len(guardians)]
        scheduled = now + dt.timedelta(minutes=off)
        student_n = (i % 3) + 1
        records.append(
            {
                "external_appointment_id": f"SEED-{i + 1:03d}",
                "booking_number": f"BKG-{2000 + i}",
                "guardian_external_id": g[0],
                "guardian_name": g[1],
                "guardian_phone": g[2],
                "student_external_id": f"{g[0]}-S{student_n}",
                "student_name": f"Student {student_n} ({g[1]})",
                "scheduled_at": scheduled,
                "source_updated_at": scheduled,
                "cancelled": False,
                "source_payload": {"seed": True, "seq": i},
            }
        )
    return records
