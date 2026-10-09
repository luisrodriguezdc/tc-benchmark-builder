"""Screen A — batch dashboard."""

from __future__ import annotations

import streamlit as st

from app.core.allocation import (
    batch_progress,
    claim_batch,
    claimable_for_pair,
    list_batches,
    list_language_pairs,
    list_public_profiles,
    pair_label,
)
from app.core.auth import Profile
from app.ui.components import render_header
from app.ui import styles


def _status_label(status: str, owner_id: str | None, me: str) -> str:
    if status == "active":
        return "In progress"
    if status == "completed":
        return "Completed"
    if status == "released":
        return "Released"
    return status


def render_dashboard(client, profile: Profile) -> None:
    styles.inject()
    render_header(profile, extra=f"Linguist: {profile.display_name}")

    pairs = list_language_pairs(client)
    claimable_pairs = []
    for pair in pairs:
        try:
            remaining = claimable_for_pair(client, pair["id"])
        except Exception:
            remaining = 0
        if remaining > 0:
            claimable_pairs.append((pair, remaining))

    st.markdown("#### Claim Next Batch")
    if not claimable_pairs:
        st.info("No language pairs currently have segments you can claim.")
    else:
        labels = {
            f"{pair_label(p)} — {n} segment(s) available": (p, n) for p, n in claimable_pairs
        }
        choice = st.selectbox("Language pair", list(labels.keys()))
        if st.button("Claim Next Batch", type="primary"):
            pair, _ = labels[choice]
            try:
                batch_id = claim_batch(client, pair["id"])
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state.batch_id = batch_id
                st.session_state.page = "workspace"
                st.rerun()

    st.divider()
    my_only = st.checkbox('Filter "my batches"', value=True)
    batches = list_batches(client)
    profiles = list_public_profiles(client)
    if my_only:
        batches = [b for b in batches if b.get("owner_id") == profile.id]

    rows = []
    for b in batches:
        lp = b.get("language_pairs") or {}
        owner = profiles.get(b["owner_id"], {})
        try:
            resolved, total = batch_progress(client, b["id"], b["owner_id"])
        except Exception:
            resolved, total = 0, 0
        status = _status_label(b["status"], b["owner_id"], profile.id)
        if b["owner_id"] == profile.id and b["status"] == "active":
            action = "Resume"
        elif b["owner_id"] == profile.id:
            action = "View"
        else:
            action = "—"
        rows.append(
            {
                "Language pair": pair_label(lp) if lp else "",
                "Batch": b.get("batch_number"),
                "Size": total,
                "Status": status,
                "Owner": owner.get("display_name") or "—",
                "Progress": f"{resolved} / {total}",
                "Action": action,
                "_id": b["id"],
                "_mine": b["owner_id"] == profile.id,
            }
        )

    if not rows:
        st.caption("No batches to show. Claim a batch above, or turn off the My Batches filter.")
        return

    st.dataframe(
        [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in rows
        ],
        hide_index=True,
        use_container_width=True,
    )

    mine = [r for r in rows if r["_mine"]]
    if mine:
        labels = {f"Batch {r['Batch']} ({r['Status']})": r["_id"] for r in mine}
        selected = st.selectbox("Open one of your batches", list(labels.keys()))
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Resume / View", type="primary"):
                st.session_state.batch_id = labels[selected]
                st.session_state.page = "workspace"
                st.rerun()
