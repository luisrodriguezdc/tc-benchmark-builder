#!/usr/bin/env python3
"""Import the 50-segment Spanish Mentoring Guidelines pilot CSV."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from app.core.config import get_settings
from app.core.db import create_service_client
from app.core.importer import parse_and_persist
from app.core.store import PostgresStore, SupabaseStore


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "data" / "tc_spanish_v3_codex_pilot.csv"
    if not csv_path.exists():
        sys.exit(f"Missing {csv_path}")

    settings = get_settings()
    if settings.database_url:
        import psycopg2

        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        store = PostgresStore(conn)
        backend = "postgres"
    else:
        store = SupabaseStore(create_service_client(settings))
        backend = "supabase"

    report = parse_and_persist(store, csv_path, publish=True)
    print(f"Imported via {backend}: {csv_path.name}")
    print(
        f"  datasets={report.datasets_upserted} segments={report.segments_upserted} "
        f"inserted={report.candidates_inserted} updated={report.candidates_updated} "
        f"versioned={report.candidates_versioned} skipped={report.candidates_skipped}"
    )
    if report.errors:
        print("Errors:")
        for e in report.errors:
            print(" ", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
