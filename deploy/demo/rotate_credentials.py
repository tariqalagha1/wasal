"""Rotate all seeded QMS demo credentials to strong temporary values.

Connects to the isolated demo DB, generates a strong password per account,
updates the bcrypt hash, and writes the credentials to a gitignored file
(CUSTOMER_CREDENTIALS.txt) that is never committed.
"""
import secrets
import string
from pathlib import Path

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "mysql+asyncmy://qms_demo_user:{pw}@127.0.0.1:3308/qms_demo?charset=utf8mb4"
OUT = Path(__file__).resolve().parent / "CUSTOMER_CREDENTIALS.txt"

USERS = ["admin", "reception", "WIN1", "WIN2", "WIN3", "WIN4"]

ROLE_DISPLAY = {
    "admin": "ADMIN (management, reports, import, audit)",
    "reception": "RECEPTIONIST (check-in, walk-in)",
    "WIN1": "CASHIER — WINDOW 1",
    "WIN2": "CASHIER — WINDOW 2",
    "WIN3": "CASHIER — WINDOW 3",
    "WIN4": "CASHIER — WINDOW 4",
}


def strong_password(length: int = 20) -> str:
    # Exclude '#' and ':' so passwords never collide with the creds-file
    # delimiters (username:password  # comment).
    alphabet = string.ascii_letters + string.digits + "!@$%^&*()-_=+"
    pw = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@$%^&*"),
    ]
    pw += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pw)
    return "".join(pw)


async def main() -> None:
    import os

    db_pw = os.environ["DEMO_DB_PASSWORD"]
    engine = create_async_engine(DB_URL.format(pw=db_pw))

    lines = []
    async with engine.begin() as conn:
        for username in USERS:
            pw = strong_password()
            hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
            await conn.execute(
                text("UPDATE users SET password_hash = :h WHERE username = :u"), {"h": hashed, "u": username}
            )
            lines.append(f"{username}: {pw}   # {ROLE_DISPLAY[username]}")
    await engine.dispose()

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.chmod(0o600)
    print(f"Rotated {len(USERS)} accounts. Credentials written to {OUT} (mode 600, gitignored).")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
