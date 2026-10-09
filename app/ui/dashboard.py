"""Screen A — batch dashboard."""

from __future__ import annotations

import streamlit as st

from app.core.allocation import (
    batch_segment_progress,
    claim_batch,
    claimable_for_pair,
    list_batches,
    list_language_pairs,
    list_public_profiles,
    pair_label,
)
from app.core.auth import Profile
from app.core.demo import demo_enabled
from app.ui.components import render_header
from app.ui import styles

DUMMY_BATCHES = [
    {"pair": "English → French", "batch": "1", "size": "40", "status": "Not started", "owner": "—", "progress": "0 / 40", "claimable": True},
    {"pair": "English → Portuguese", "batch": "1", "size": "36", "status": "WIP", "owner": "Miguel Santos", "progress": "11 / 36", "claimable": False},
    {"pair": "English → German", "batch": "1", "size": "40", "status": "Not started", "owner": "—", "progress": "0 / 40", "claimable": True},
    {"pair": "English → Italian", "batch": "1", "size": "32", "status": "Completed", "owner": "Giulia Romano", "progress": "32 / 32", "claimable": False},
    {"pair": "English → Dutch", "batch": "1", "size": "28", "status": "Not started", "owner": "—", "progress": "0 / 28", "claimable": True},
    {"pair": "English → Polish", "batch": "1", "size": "30", "status": "WIP", "owner": "Anna Kowalska", "progress": "7 / 30", "claimable": False},
    {"pair": "English → Chinese", "batch": "1", "size": "45", "status": "Not started", "owner": "—", "progress": "0 / 45", "claimable": True},
    {"pair": "English → Japanese", "batch": "1", "size": "38", "status": "Not started", "owner": "—", "progress": "0 / 38", "claimable": True},
    {"pair": "English → Korean", "batch": "1", "size": "34", "status": "WIP", "owner": "Min-jun Park", "progress": "16 / 34", "claimable": False},
    {"pair": "English → Arabic", "batch": "1", "size": "42", "status": "Not started", "owner": "—", "progress": "0 / 42", "claimable": True},
    {"pair": "English → Hindi", "batch": "1", "size": "30", "status": "Completed", "owner": "Priya Shah", "progress": "30 / 30", "claimable": False},
]


def _status_label(status: str) -> str:
    if status == "active":
        return "WIP"
    if status == "completed":
        return "Completed"
    if status == "released":
        return "Released"
    return status


def render_dashboard(client, profile: Profile) -> None:
    styles.inject()
    render_header()

    st.markdown('<div class="tcb-title">Batches</div>', unsafe_allow_html=True)
    if st.session_state.get("claim_error"):
        st.markdown(
            f'<div class="tcb-alert warn" role="alert">{st.session_state.claim_error}</div>',
            unsafe_allow_html=True,
        )

    rows = _catalog_rows(client, profile)
    all_tab, mine_tab = st.tabs(["All Batches", "My Batches"])
    with all_tab:
        _render_table(client, rows, key_prefix="all")
    with mine_tab:
        mine = [r for r in rows if r.get("_mine")]
        if not mine:
            st.caption("You have no batches yet. Claim one from All Batches.")
        else:
            _render_table(client, mine, key_prefix="mine")


def _catalog_rows(client, profile: Profile) -> list[dict]:
    profiles = list_public_profiles(client)
    batches = list_batches(client)
    pairs = list_language_pairs(client)
    rows: list[dict] = []

    if demo_enabled():
        rows.append(
            {
                "pair": "English → Spanish",
                "batch": "1",
                "size": "50",
                "status": "WIP",
                "owner": "Elena Vargas",
                "progress": "18 / 50",
                "action": "none",
                "_mine": False,
            }
        )

    has_active = any(b.get("owner_id") == profile.id and b.get("status") == "active" for b in batches)

    for b in batches:
        lp = b.get("language_pairs") or {}
        owner = profiles.get(b["owner_id"], {})
        try:
            resolved, total = batch_segment_progress(client, b["id"], b["owner_id"])
        except Exception:
            resolved, total = 0, 0
        status = _status_label(b["status"])
        if b["owner_id"] == profile.id and b["status"] == "active":
            action = "resume"
        elif b["owner_id"] == profile.id:
            action = "view"
        else:
            action = "none"
        batch_no = int(b.get("batch_number") or 0)
        if demo_enabled() and (lp.get("target_lang") in {"es-ES", "es"}):
            batch_no += 1
        rows.append(
            {
                "pair": pair_label(lp) if lp else "",
                "batch": str(batch_no),
                "size": str(total),
                "status": status,
                "owner": owner.get("display_name") or "—",
                "progress": f"{resolved} / {total}",
                "action": action,
                "_id": b["id"],
                "_mine": b["owner_id"] == profile.id,
            }
        )

    for pair in pairs:
        remaining = 0
        try:
            remaining = claimable_for_pair(client, pair["id"])
        except Exception:
            remaining = 0
        if remaining <= 0 or has_active:
            continue
        size = int(pair.get("batch_size") or remaining)
        size = min(size, remaining)
        next_num = 1 + max(
            (int(b.get("batch_number") or 0) for b in batches if b.get("language_pair_id") == pair["id"]),
            default=0,
        )
        if demo_enabled() and pair.get("target_lang") in {"es-ES", "es"}:
            next_num = max(next_num, 2)
        rows.append(
            {
                "pair": pair_label(pair),
                "batch": str(next_num),
                "size": str(size),
                "status": "Not started",
                "owner": "—",
                "progress": f"0 / {size}",
                "action": "claim",
                "_pair_id": pair["id"],
                "_mine": False,
            }
        )

    if demo_enabled():
        for dummy in DUMMY_BATCHES:
            rows.append(
                {
                    **dummy,
                    "action": "claim-dummy" if dummy["claimable"] else "none",
                    "_mine": False,
                }
            )

    return rows


def _render_table(client, rows: list[dict], key_prefix: str) -> None:
    header = st.columns([2.3, 0.7, 0.7, 1.2, 1.7, 1.0, 1.5])
    labels = ["Language pair", "Batch", "Size", "Status", "Owner", "Progress", "Action"]
    for col, label in zip(header, labels):
        col.markdown(f"**{label}**")
    st.markdown(
        '<hr style="margin:0.2rem 0 0.35rem;border:0;border-top:1px solid rgba(49,51,63,0.12);">',
        unsafe_allow_html=True,
    )

    for i, row in enumerate(rows):
        cols = st.columns([2.3, 0.7, 0.7, 1.2, 1.7, 1.0, 1.5])
        cols[0].write(row["pair"])
        cols[1].write(row["batch"])
        cols[2].write(row["size"])
        cols[3].markdown(styles.status_pill(row["status"]), unsafe_allow_html=True)
        cols[4].write(row["owner"])
        cols[5].write(row["progress"])
        with cols[6]:
            _row_action(client, row, f"{key_prefix}_{i}")


def _row_action(client, row: dict, index: str) -> None:
    action = row.get("action")
    if action == "claim":
        if st.button("Claim This Batch", key=f"claim_{index}", type="primary"):
            _do_claim(client, row["_pair_id"])
        return
    if action == "claim-dummy":
        if st.button("Claim This Batch", key=f"claim_{index}", type="primary"):
            st.session_state.claim_error = "Only the English → Spanish sample includes segments in this demo."
            st.rerun()
        return
    if action in ("resume", "view"):
        label = "Resume" if action == "resume" else "View"
        if st.button(label, key=f"open_{index}"):
            st.session_state.claim_error = ""
            st.session_state.batch_id = row["_id"]
            st.session_state.page = "workspace"
            st.session_state.pop("ws_pos", None)
            st.rerun()
        return
    st.write("—")


def _do_claim(client, pair_id: str) -> None:
    st.session_state.claim_error = ""
    try:
        batch_id = claim_batch(client, pair_id)
    except Exception as exc:
        st.session_state.claim_error = str(exc).rstrip(".") + "."
        st.rerun()
        return
    st.session_state.batch_id = batch_id
    st.session_state.page = "workspace"
    st.session_state.pop("ws_pos", None)
    st.rerun()
