"""CSV export builders for admin review."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

EXPORT_COLUMNS = [
    "annotation_id",
    "candidate_id",
    "candidate_external_id",
    "candidate_version",
    "segment_external_id",
    "dataset_name",
    "dataset_version",
    "language_pair",
    "batch_id",
    "batch_number",
    "annotator_id",
    "annotator_email",
    "annotator_name",
    "status",
    "original_text",
    "edited_text",
    "original_error_type",
    "final_error_type",
    "original_severity",
    "final_severity",
    "rejection_reason",
    "comment",
    "created_at",
    "updated_at",
    "source_text",
    "reference_text",
    "source_error",
]


def rows_to_csv(rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> str:
    fieldnames = fieldnames or EXPORT_COLUMNS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def fetch_export_rows(client, *, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    anns = client.table("annotations").select("*").execute().data or []
    if filters.get("status"):
        anns = [a for a in anns if a.get("status") == filters["status"]]
    if filters.get("annotator_id"):
        anns = [a for a in anns if a.get("annotator_id") == filters["annotator_id"]]
    if filters.get("error_type"):
        anns = [a for a in anns if a.get("error_type") == filters["error_type"]]
    if not anns:
        return []

    cand_ids = list({a["candidate_id"] for a in anns})
    batch_ids = list({a["batch_id"] for a in anns})
    annotator_ids = list({a["annotator_id"] for a in anns})

    candidates = _in_query(client, "error_candidates", "id", cand_ids)
    batches = _in_query(client, "batches", "id", batch_ids)
    profiles = _in_query(client, "profiles", "id", annotator_ids)

    cand_by_id = {c["id"]: c for c in candidates}
    batch_by_id = {b["id"]: b for b in batches}
    profile_by_id = {p["id"]: p for p in profiles}

    segment_ids = list({c["segment_id"] for c in candidates})
    segments = _in_query(client, "segments", "id", segment_ids)
    seg_by_id = {s["id"]: s for s in segments}
    batch_items = _in_query(client, "batch_items", "batch_id", batch_ids)
    source_error_by_key = {
        (i.get("batch_id"), i.get("segment_id")): bool(i.get("source_error")) for i in batch_items
    }

    dataset_ids = list({s["dataset_id"] for s in segments})
    datasets = _in_query(client, "datasets", "id", dataset_ids)
    ds_by_id = {d["id"]: d for d in datasets}

    pair_ids = list({d["language_pair_id"] for d in datasets} | {b["language_pair_id"] for b in batches})
    pairs = _in_query(client, "language_pairs", "id", pair_ids)
    pair_by_id = {p["id"]: p for p in pairs}

    if filters.get("batch_id"):
        anns = [a for a in anns if a.get("batch_id") == filters["batch_id"]]
    if filters.get("language_pair_id"):
        anns = [
            a
            for a in anns
            if batch_by_id.get(a["batch_id"], {}).get("language_pair_id") == filters["language_pair_id"]
        ]
    if filters.get("dataset_id"):
        anns = [
            a
            for a in anns
            if seg_by_id.get(cand_by_id.get(a["candidate_id"], {}).get("segment_id"), {}).get("dataset_id")
            == filters["dataset_id"]
        ]

    out = []
    for a in anns:
        cand = cand_by_id.get(a["candidate_id"], {})
        seg = seg_by_id.get(cand.get("segment_id"), {})
        ds = ds_by_id.get(seg.get("dataset_id"), {})
        batch = batch_by_id.get(a["batch_id"], {})
        pair = pair_by_id.get(batch.get("language_pair_id") or ds.get("language_pair_id"), {})
        prof = profile_by_id.get(a["annotator_id"], {})
        out.append(
            {
                "annotation_id": a.get("id"),
                "candidate_id": cand.get("id"),
                "candidate_external_id": cand.get("external_id"),
                "candidate_version": cand.get("version"),
                "segment_external_id": seg.get("external_id"),
                "dataset_name": ds.get("name"),
                "dataset_version": ds.get("version"),
                "language_pair": f"{pair.get('source_lang', '')}→{pair.get('target_lang', '')}",
                "batch_id": batch.get("id"),
                "batch_number": batch.get("batch_number"),
                "annotator_id": prof.get("id"),
                "annotator_email": prof.get("email"),
                "annotator_name": prof.get("display_name"),
                "status": a.get("status"),
                "original_text": cand.get("generated_text"),
                "edited_text": a.get("edited_text"),
                "original_error_type": cand.get("error_type"),
                "final_error_type": a.get("error_type"),
                "original_severity": cand.get("severity"),
                "final_severity": a.get("severity"),
                "rejection_reason": a.get("rejection_reason") or "",
                "comment": a.get("comment") or "",
                "created_at": a.get("created_at"),
                "updated_at": a.get("updated_at"),
                "source_text": seg.get("source_text"),
                "reference_text": seg.get("reference_text"),
                "source_error": source_error_by_key.get((a.get("batch_id"), cand.get("segment_id")), False),
            }
        )
    return out


def fetch_suggestions(client) -> list[dict[str, Any]]:
    rows = client.table("error_suggestions").select("*").execute().data or []
    if not rows:
        return []
    author_ids = list({r["author_id"] for r in rows})
    profiles = {p["id"]: p for p in _in_query(client, "profiles", "id", author_ids)}
    out = []
    for r in rows:
        prof = profiles.get(r["author_id"], {})
        out.append(
            {
                "suggestion_id": r["id"],
                "segment_id": r["segment_id"],
                "batch_id": r["batch_id"],
                "author_id": r["author_id"],
                "author_email": prof.get("email"),
                "author_name": prof.get("display_name"),
                "suggested_text": r["suggested_text"],
                "error_type": r["error_type"],
                "severity": r["severity"],
                "notes": r.get("notes") or "",
                "created_at": r["created_at"],
            }
        )
    return out


def fetch_iaa_disagreements(client) -> list[dict[str, Any]]:
    rows = client.table("iaa_agreements").select("*").execute().data or []
    return [r for r in rows if not r.get("status_agree") or r.get("type_agree") is False or r.get("severity_agree") is False]


def _in_query(client, table: str, column: str, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    # PostgREST IN filters can be chunked for safety.
    out: list[dict] = []
    chunk = 200
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        res = client.table(table).select("*").in_(column, part).execute()
        out.extend(res.data or [])
    return out
