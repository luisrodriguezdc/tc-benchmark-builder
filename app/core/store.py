"""Persistence adapters used by the importer (Postgres for tests/scripts, Supabase for the app)."""

from __future__ import annotations

from typing import Any, Protocol

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json


class Store(Protocol):
    def find_language_pair(self, source_lang: str, target_lang: str) -> dict | None: ...
    def insert_language_pair(self, row: dict) -> dict: ...
    def find_dataset(self, pair_id: str, name: str, version: str) -> dict | None: ...
    def upsert_dataset(self, row: dict) -> dict: ...
    def find_segment(self, dataset_id: str, external_id: str) -> dict | None: ...
    def upsert_segment(self, row: dict) -> dict: ...
    def find_candidate(self, segment_id: str, external_id: str) -> dict | None: ...
    def candidate_is_assigned(self, candidate_id: str) -> bool: ...
    def insert_candidate(self, row: dict) -> dict: ...
    def update_candidate(self, candidate_id: str, row: dict) -> dict: ...
    def max_candidate_version(self, segment_id: str, external_id: str) -> int: ...


class PostgresStore:
    def __init__(self, conn):
        self.conn = conn

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def _exec(self, sql: str, params: tuple = ()) -> dict | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description:
                row = cur.fetchone()
                return dict(row) if row else None
            return None

    def find_language_pair(self, source_lang: str, target_lang: str) -> dict | None:
        return self._one(
            "SELECT * FROM language_pairs WHERE source_lang = %s AND target_lang = %s",
            (source_lang, target_lang),
        )

    def insert_language_pair(self, row: dict) -> dict:
        found = self.find_language_pair(row["source_lang"], row["target_lang"])
        if found:
            return found
        created = self._exec(
            """
            INSERT INTO language_pairs
              (source_lang, target_lang, source_label, target_label, iaa_target_pct, batch_size, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                row["source_lang"],
                row["target_lang"],
                row.get("source_label") or "",
                row.get("target_label") or "",
                row.get("iaa_target_pct", 15),
                row.get("batch_size", 100),
                row.get("is_active", True),
            ),
        )
        assert created
        return created

    def find_dataset(self, pair_id: str, name: str, version: str) -> dict | None:
        return self._one(
            "SELECT * FROM datasets WHERE language_pair_id = %s AND name = %s AND version = %s",
            (pair_id, name, version),
        )

    def upsert_dataset(self, row: dict) -> dict:
        existing = self.find_dataset(row["language_pair_id"], row["name"], row["version"])
        if existing:
            updated = self._exec(
                """
                UPDATE datasets SET status = %s, notes = %s
                WHERE id = %s
                RETURNING *
                """,
                (row.get("status", existing["status"]), row.get("notes"), existing["id"]),
            )
            return updated or existing
        created = self._exec(
            """
            INSERT INTO datasets (language_pair_id, name, version, status, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                row["language_pair_id"],
                row["name"],
                row["version"],
                row.get("status", "draft"),
                row.get("notes"),
            ),
        )
        assert created
        return created

    def find_segment(self, dataset_id: str, external_id: str) -> dict | None:
        return self._one(
            "SELECT * FROM segments WHERE dataset_id = %s AND external_id = %s",
            (dataset_id, external_id),
        )

    def upsert_segment(self, row: dict) -> dict:
        existing = self.find_segment(row["dataset_id"], row["external_id"])
        if existing:
            updated = self._exec(
                """
                UPDATE segments
                SET source_text = %s, reference_text = %s, sample_order = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    row["source_text"],
                    row["reference_text"],
                    row.get("sample_order", 0),
                    existing["id"],
                ),
            )
            return updated or existing
        created = self._exec(
            """
            INSERT INTO segments (dataset_id, external_id, source_text, reference_text, sample_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                row["dataset_id"],
                row["external_id"],
                row["source_text"],
                row["reference_text"],
                row.get("sample_order", 0),
            ),
        )
        assert created
        return created

    def find_candidate(self, segment_id: str, external_id: str) -> dict | None:
        return self._one(
            """
            SELECT * FROM error_candidates
            WHERE segment_id = %s AND external_id = %s
            ORDER BY version DESC
            LIMIT 1
            """,
            (segment_id, external_id),
        )

    def candidate_is_assigned(self, candidate_id: str) -> bool:
        row = self._one(
            "SELECT 1 AS ok FROM batch_item_candidates WHERE candidate_id = %s LIMIT 1",
            (candidate_id,),
        )
        return row is not None

    def insert_candidate(self, row: dict) -> dict:
        created = self._exec(
            """
            INSERT INTO error_candidates (
              segment_id, external_id, version, status, error_type, severity,
              generated_text, target_span_start, target_span_end, ref_span_start,
              ref_span_end, target_insert_pos, metadata
            ) VALUES (
              %(segment_id)s, %(external_id)s, %(version)s, %(status)s, %(error_type)s,
              %(severity)s, %(generated_text)s, %(target_span_start)s, %(target_span_end)s,
              %(ref_span_start)s, %(ref_span_end)s, %(target_insert_pos)s, %(metadata)s
            )
            RETURNING *
            """,
            _psycopg_adapt(row),
        )
        assert created
        return created

    def update_candidate(self, candidate_id: str, row: dict) -> dict:
        updated = self._exec(
            """
            UPDATE error_candidates SET
              status = %(status)s,
              error_type = %(error_type)s,
              severity = %(severity)s,
              generated_text = %(generated_text)s,
              target_span_start = %(target_span_start)s,
              target_span_end = %(target_span_end)s,
              ref_span_start = %(ref_span_start)s,
              ref_span_end = %(ref_span_end)s,
              target_insert_pos = %(target_insert_pos)s,
              metadata = %(metadata)s
            WHERE id = %(id)s
            RETURNING *
            """,
            _psycopg_adapt({**row, "id": candidate_id}),
        )
        assert updated
        return updated

    def max_candidate_version(self, segment_id: str, external_id: str) -> int:
        row = self._one(
            """
            SELECT coalesce(max(version), 0) AS v
            FROM error_candidates
            WHERE segment_id = %s AND external_id = %s
            """,
            (segment_id, external_id),
        )
        return int(row["v"]) if row else 0


def _psycopg_adapt(row: dict) -> dict:
    adapted = dict(row)
    meta = adapted.get("metadata")
    if isinstance(meta, dict):
        adapted["metadata"] = Json(meta)
    return adapted


class SupabaseStore:
    def __init__(self, client):
        self.client = client

    def find_language_pair(self, source_lang: str, target_lang: str) -> dict | None:
        res = (
            self.client.table("language_pairs")
            .select("*")
            .eq("source_lang", source_lang)
            .eq("target_lang", target_lang)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]

    def insert_language_pair(self, row: dict) -> dict:
        found = self.find_language_pair(row["source_lang"], row["target_lang"])
        if found:
            return found
        res = self.client.table("language_pairs").insert(row).execute()
        return res.data[0]

    def find_dataset(self, pair_id: str, name: str, version: str) -> dict | None:
        res = (
            self.client.table("datasets")
            .select("*")
            .eq("language_pair_id", pair_id)
            .eq("name", name)
            .eq("version", version)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]

    def upsert_dataset(self, row: dict) -> dict:
        existing = self.find_dataset(row["language_pair_id"], row["name"], row["version"])
        if existing:
            res = (
                self.client.table("datasets")
                .update({"status": row.get("status", existing["status"]), "notes": row.get("notes")})
                .eq("id", existing["id"])
                .execute()
            )
            return (res.data or [existing])[0]
        res = self.client.table("datasets").insert(row).execute()
        return res.data[0]

    def find_segment(self, dataset_id: str, external_id: str) -> dict | None:
        res = (
            self.client.table("segments")
            .select("*")
            .eq("dataset_id", dataset_id)
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]

    def upsert_segment(self, row: dict) -> dict:
        existing = self.find_segment(row["dataset_id"], row["external_id"])
        if existing:
            res = (
                self.client.table("segments")
                .update(
                    {
                        "source_text": row["source_text"],
                        "reference_text": row["reference_text"],
                        "sample_order": row.get("sample_order", 0),
                    }
                )
                .eq("id", existing["id"])
                .execute()
            )
            return (res.data or [existing])[0]
        res = self.client.table("segments").insert(row).execute()
        return res.data[0]

    def find_candidate(self, segment_id: str, external_id: str) -> dict | None:
        res = (
            self.client.table("error_candidates")
            .select("*")
            .eq("segment_id", segment_id)
            .eq("external_id", external_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]

    def candidate_is_assigned(self, candidate_id: str) -> bool:
        res = (
            self.client.table("batch_item_candidates")
            .select("candidate_id")
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def insert_candidate(self, row: dict) -> dict:
        res = self.client.table("error_candidates").insert(row).execute()
        return res.data[0]

    def update_candidate(self, candidate_id: str, row: dict) -> dict:
        payload = {k: v for k, v in row.items() if k != "id"}
        res = self.client.table("error_candidates").update(payload).eq("id", candidate_id).execute()
        return res.data[0]

    def max_candidate_version(self, segment_id: str, external_id: str) -> int:
        res = (
            self.client.table("error_candidates")
            .select("version")
            .eq("segment_id", segment_id)
            .eq("external_id", external_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return int(rows[0]["version"]) if rows else 0
