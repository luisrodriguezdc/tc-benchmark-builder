"""Annotation load/save with optimistic concurrency."""

from __future__ import annotations

from typing import Any

from supabase import Client


class VersionConflict(Exception):
    """Raised when another session saved the same annotation first."""


def _rpc_error_is_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return "version_conflict" in text or "40001" in text


def save_annotation(
    client: Client,
    *,
    candidate_id: str,
    batch_id: str,
    status: str,
    edited_text: str,
    error_type: str,
    severity: str,
    rejection_reason: str | None,
    comment: str | None,
    expected_version: int,
) -> dict[str, Any]:
    try:
        res = client.rpc(
            "save_annotation",
            {
                "p_candidate_id": candidate_id,
                "p_batch_id": batch_id,
                "p_status": status,
                "p_edited_text": edited_text,
                "p_error_type": error_type,
                "p_severity": severity,
                "p_rejection_reason": rejection_reason,
                "p_comment": comment,
                "p_expected_version": expected_version,
            },
        ).execute()
    except Exception as exc:
        if _rpc_error_is_conflict(exc):
            raise VersionConflict(str(exc)) from exc
        raise
    data = res.data
    if isinstance(data, list):
        data = data[0] if data else {}
    return data or {}


def flag_source_error(
    client: Client,
    *,
    batch_id: str,
    segment_id: str,
    flagged: bool,
) -> None:
    client.rpc(
        "flag_source_error",
        {
            "p_batch_id": batch_id,
            "p_segment_id": segment_id,
            "p_flagged": flagged,
        },
    ).execute()


def submit_suggestion(
    client: Client,
    *,
    segment_id: str,
    batch_id: str,
    suggested_text: str,
    error_type: str,
    severity: str,
    notes: str | None,
) -> str:
    res = client.rpc(
        "submit_error_suggestion",
        {
            "p_segment_id": segment_id,
            "p_batch_id": batch_id,
            "p_suggested_text": suggested_text,
            "p_error_type": error_type,
            "p_severity": severity,
            "p_notes": notes,
        },
    ).execute()
    return str(res.data)


def load_workspace(client: Client, batch_id: str, annotator_id: str) -> dict[str, Any]:
    batch_res = (
        client.table("batches")
        .select("*, language_pairs(source_lang,target_lang,source_label,target_label)")
        .eq("id", batch_id)
        .limit(1)
        .execute()
    )
    if not batch_res.data:
        raise RuntimeError("Batch not found.")
    batch = batch_res.data[0]
    items = (
        client.table("batch_items")
        .select("*")
        .eq("batch_id", batch_id)
        .order("position")
        .execute()
        .data
        or []
    )
    if not items:
        return {"batch": batch, "items": []}

    segment_ids = [i["segment_id"] for i in items]
    segments = (
        client.table("segments")
        .select("*")
        .in_("id", segment_ids)
        .execute()
        .data
        or []
    )
    seg_by_id = {s["id"]: s for s in segments}

    item_ids = [i["id"] for i in items]
    pinned = (
        client.table("batch_item_candidates")
        .select("batch_item_id,candidate_id")
        .in_("batch_item_id", item_ids)
        .execute()
        .data
        or []
    )
    cand_ids = [p["candidate_id"] for p in pinned]
    candidates = (
        client.table("error_candidates").select("*").in_("id", cand_ids).execute().data or []
        if cand_ids
        else []
    )
    cand_by_id = {c["id"]: c for c in candidates}

    anns = (
        client.table("annotations")
        .select("*")
        .eq("annotator_id", annotator_id)
        .eq("batch_id", batch_id)
        .execute()
        .data
        or []
    )
    ann_by_cand = {a["candidate_id"]: a for a in anns}

    suggestions = (
        client.table("error_suggestions")
        .select("*")
        .eq("batch_id", batch_id)
        .eq("author_id", annotator_id)
        .execute()
        .data
        or []
    )
    sugg_by_seg: dict[str, list] = {}
    for s in suggestions:
        sugg_by_seg.setdefault(s["segment_id"], []).append(s)

    pin_by_item: dict[str, list] = {}
    for p in pinned:
        pin_by_item.setdefault(p["batch_item_id"], []).append(cand_by_id[p["candidate_id"]])

    packed = []
    for item in items:
        cands = pin_by_item.get(item["id"], [])
        packed.append(
            {
                "item": item,
                "segment": seg_by_id.get(item["segment_id"]),
                "candidates": cands,
                "annotations": {c["id"]: ann_by_cand.get(c["id"]) for c in cands},
                "suggestions": sugg_by_seg.get(item["segment_id"], []),
            }
        )
    return {"batch": batch, "items": packed}


def annotation_counts(items: list[dict]) -> dict[str, int]:
    validated = rejected = incomplete = 0
    for item in items:
        if (item.get("item") or {}).get("source_error"):
            continue
        for cand in item["candidates"]:
            ann = item["annotations"].get(cand["id"])
            status = (ann or {}).get("status") or "draft"
            if status == "validated":
                validated += 1
            elif status == "rejected":
                rejected += 1
            else:
                incomplete += 1
    return {"validated": validated, "rejected": rejected, "incomplete": incomplete}
