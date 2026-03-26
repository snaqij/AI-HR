"""Simple database connectivity check script for AI-HR."""

from __future__ import annotations

import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from ai_hr.core.config import get_settings
from ai_hr.db.session import engine


def _safe_database_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.password is None:
        return str(parsed)
    return str(parsed.set(password="***"))


def _current_database_sql(dialect_name: str) -> str | None:
    if dialect_name in {"mysql", "mariadb"}:
        return "SELECT DATABASE()"
    if dialect_name == "postgresql":
        return "SELECT current_database()"
    if dialect_name == "sqlite":
        return "SELECT 'sqlite'"
    return None


def main() -> int:
    settings = get_settings()
    safe_url = _safe_database_url(settings.database_url)
    print(f"[DB CHECK] Using database URL: {safe_url}")

    try:
        with engine.connect() as connection:
            ping = connection.execute(text("SELECT 1")).scalar_one()

            current_db = None
            database_sql = _current_database_sql(engine.dialect.name)
            if database_sql:
                current_db = connection.execute(text(database_sql)).scalar_one_or_none()

            print("[DB CHECK] Connection successful.")
            print(f"[DB CHECK] Dialect: {engine.dialect.name}")
            print(f"[DB CHECK] Ping result: {ping}")
            if current_db:
                print(f"[DB CHECK] Current database: {current_db}")
            return 0
    except Exception as exc:  # noqa: BLE001
        print("[DB CHECK] Connection failed.")
        print(f"[DB CHECK] Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
