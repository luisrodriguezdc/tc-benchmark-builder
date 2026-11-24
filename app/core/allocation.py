"""Wrappers around claim_batch and dashboard queries."""

from __future__ import annotations

import math
from typing import Any

from supabase import Client


def pair_label(pair: dict) -> str:
    src = pair.get("source_label") or pair.get("source_lang")
    tgt = pair.get("target_label") or pair.get("target_lang")
    return f"{src} → {tgt}"


def list_assigned_pair_ids(client: Client, profile_id: str) -> set[str]:
    res = (
        client.table("translator_languages")
        .select("language_pair_id")
        .eq("profile_id", profile_id)
        .execute()
    )
    return {str(row["language_pair_id"]) for row in (res.data or []) if row.get("language_pair_id")}


def list_language_pairs(client: Client, *, active_only: bool = True) -> list[dict]:
    q = client.table("language_pairs").select("*")
    if active_only:
        q = q.eq("is_active", True)
    res = q.order("source_lang").execute()
    return res.data or []


def next_open_batch_number(taken) -> int:
    """Smallest batch number that is not already claimed.

    A released batch is deleted, so its number is open again. A later batch
    that is still claimed does not push the next claim past that gap.
    """
    used = {int(number) for number in taken if int(number) > 0}
    number = 1
    while number in used:
        number += 1
    return number


def batch_slot_sizes(published: int, batch_size: int) -> list[int]:
    """Planned batch sizes for a language. The last slot holds the remainder."""
    if published <= 0 or batch_size <= 0:
        return []
    slots = math.ceil(published / batch_size)
    sizes: list[int] = []
    remaining = published
    for index in range(slots):
        size = batch_size if index < slots - 1 else remaining
        sizes.append(size)
        remaining -= size
    return sizes


def published_segment_counts(client: Client) -> dict[str, int]:
    """Published segments per language pair.

    The in-memory demo can see every row. A signed-in volunteer cannot:
    segment rows outside their own batches are hidden. ``iaa_pair_stats`` is
    the aggregate already granted to signed-in users, and its count is only
    segments in published datasets that have a published candidate.
    """
    store = getattr(client, "_store", None)
    if store is not None:
        return _published_counts_from_tables(store.tables)
    rows = client.table("iaa_pair_stats").select("language_pair_id,unique_segments").execute().data or []
    return {str(row["language_pair_id"]): int(row.get("unique_segments") or 0) for row in rows}


def _published_counts_from_tables(tables: dict[str, list]) -> dict[str, int]:
    published_datasets = {
        dataset["id"]: dataset["language_pair_id"]
        for dataset in tables.get("datasets", [])
        if dataset.get("status") == "published" and dataset.get("language_pair_id")
    }
    published_segments = {
        candidate["segment_id"]
        for candidate in tables.get("error_candidates", [])
        if candidate.get("status") == "published" and candidate.get("segment_id")
    }
    counts: dict[str, int] = {}
    for segment in tables.get("segments", []):
        pair_id = published_datasets.get(segment.get("dataset_id"))
        if pair_id and segment.get("id") in published_segments:
            key = str(pair_id)
            counts[key] = counts.get(key, 0) + 1
    return counts


def claimable_for_pair(client: Client, pair_id: str) -> int:
    res = client.rpc("claimable_count", {"p_language_pair_id": pair_id}).execute()
    data = res.data
    if data is None:
        return 0
    return int(data)


def claim_batch(client: Client, pair_id: str) -> str:
    res = client.rpc("claim_batch", {"p_language_pair_id": pair_id}).execute()
    batch_id = res.data
    if not batch_id:
        raise RuntimeError("Claim did not return a batch id.")
    return str(batch_id)


def list_batches(client: Client) -> list[dict[str, Any]]:
    res = (
        client.table("batches")
        .select("*, language_pairs(source_lang,target_lang,source_label,target_label)")
        .order("claimed_at", desc=True)
        .execute()
    )
    return res.data or []


def list_public_profiles(client: Client) -> dict[str, dict]:
    res = client.table("profiles_public").select("id,display_name,role").execute()
    return {row["id"]: row for row in (res.data or [])}


def batch_progress(client: Client, batch_id: str, owner_id: str) -> tuple[int, int]:
    items = client.table("batch_items").select("id").eq("batch_id", batch_id).execute().data or []
    if not items:
        return 0, 0
    item_ids = [i["id"] for i in items]
    pinned = (
        client.table("batch_item_candidates")
        .select("candidate_id")
        .in_("batch_item_id", item_ids)
        .execute()
        .data
        or []
    )
    total = len(pinned)
    if total == 0:
        return 0, 0
    cand_ids = [p["candidate_id"] for p in pinned]
    anns = (
        client.table("annotations")
        .select("id,status")
        .eq("annotator_id", owner_id)
        .in_("candidate_id", cand_ids)
        .execute()
        .data
        or []
    )
    resolved = sum(1 for a in anns if a["status"] in ("validated", "rejected"))
    return resolved, total


def batch_segment_progress(client: Client, batch_id: str, owner_id: str) -> tuple[int, int]:
    items = client.table("batch_items").select("id").eq("batch_id", batch_id).execute().data or []
    total = len(items)
    if not total:
        return 0, 0
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
    if not cand_ids:
        return 0, total
    anns = (
        client.table("annotations")
        .select("candidate_id,status")
        .eq("annotator_id", owner_id)
        .in_("candidate_id", cand_ids)
        .execute()
        .data
        or []
    )
    resolved_cands = {a["candidate_id"] for a in anns if a["status"] in ("validated", "rejected")}
    by_item: dict[str, list[str]] = {}
    for p in pinned:
        by_item.setdefault(p["batch_item_id"], []).append(p["candidate_id"])
    resolved = 0
    for iid in item_ids:
        cids = by_item.get(iid) or []
        if cids and all(c in resolved_cands for c in cids):
            resolved += 1
    return resolved, total


def set_batch_position(client: Client, batch_id: str, position: int) -> None:
    client.rpc("set_batch_position", {"p_batch_id": batch_id, "p_position": position}).execute()
