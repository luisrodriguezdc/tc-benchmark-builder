"""Wrappers around claim_batch and dashboard queries."""

from __future__ import annotations

from typing import Any

from supabase import Client


def pair_label(pair: dict) -> str:
    src = pair.get("source_label") or pair.get("source_lang")
    tgt = pair.get("target_label") or pair.get("target_lang")
    return f"{src} → {tgt}"


def list_language_pairs(client: Client, *, active_only: bool = True) -> list[dict]:
    q = client.table("language_pairs").select("*")
    if active_only:
        q = q.eq("is_active", True)
    res = q.order("source_lang").execute()
    return res.data or []


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
