"""Simple SQL migration runner.

Applies .sql files in migrations/ in filename order. Each migration runs inside
its own transaction when possible, and success is recorded in schema_migrations.
"""
from __future__ import annotations

import asyncio
import pathlib

from sqlalchemy import text

from app.core.db import engine

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "migrations"


async def applied_versions(conn) -> set[str]:
    try:
        res = await conn.execute(text("SELECT version FROM schema_migrations"))
        return {row[0] for row in res.fetchall()}
    except Exception:
        return set()


async def apply_migrations() -> list[str]:
    applied: list[str] = []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with engine.begin() as conn:
        existing = await applied_versions(conn)
        for f in files:
            version = f.stem
            if version in existing:
                continue
            sql = f.read_text(encoding="utf-8")
            # Split on statement boundaries (naive but sufficient for DDL files).
            for statement in _split_statements(sql):
                if statement.strip():
                    await conn.execute(text(statement))
            await conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:v)"),
                {"v": version},
            )
            applied.append(version)
    return applied


def _split_statements(sql: str) -> list[str]:
    # Our migration files only use CREATE TABLE statements and simple inserts;
    # split on ';' at end of line. Stored procedures are out of scope for V1.
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(buf))
            buf = []
    if buf:
        parts.append("\n".join(buf))
    return parts


async def main() -> None:
    applied = await apply_migrations()
    print(f"Applied migrations: {applied if applied else 'none (already up to date)'}")


if __name__ == "__main__":
    asyncio.run(main())
