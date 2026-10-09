#!/usr/bin/env python3
"""Apply SQL migrations to a Postgres database (local tests or the Supabase SQL URI)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

import psycopg2

from app.core.config import get_settings


def migration_files(root: Path) -> list[Path]:
    return sorted((root / "supabase" / "migrations").glob("*.sql"))


def apply(conn, root: Path, *, stub_auth: bool = False) -> None:
    files = []
    if stub_auth:
        files.append(root / "tests" / "sql" / "auth_stub.sql")
    files.extend(migration_files(root))
    with conn.cursor() as cur:
        for path in files:
            print(f"Applying {path.name} ...")
            cur.execute(path.read_text(encoding="utf-8"))
    conn.commit()


def main() -> None:
    settings = get_settings()
    url = settings.database_url
    if not url:
        sys.exit("DATABASE_URL is required.")
    stub = "--stub-auth" in sys.argv
    root = Path(__file__).resolve().parents[1]
    conn = psycopg2.connect(url)
    try:
        apply(conn, root, stub_auth=stub)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
