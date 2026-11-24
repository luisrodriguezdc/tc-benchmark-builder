"""Admin volunteer management."""

from __future__ import annotations

import streamlit as st

from app.core.allocation import pair_label
from app.core.auth import invite_user
from app.ui.components import render_header, render_page_title
from app.ui import styles


def _pair_option(pair: dict) -> str:
    label = f"{pair_label(pair)} ({pair['source_lang']}→{pair['target_lang']})"
    if not pair.get("is_active", True):
        label += " (inactive)"
    return label


def render_volunteers(client) -> None:
    styles.inject()
    render_header()
    render_page_title("Volunteers", admin=True)
    profiles = (
        client.table("profiles")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    batches = client.table("batches").select("id,owner_id,status,batch_number,language_pair_id").execute().data or []
    anns = client.table("annotations").select("annotator_id,status").execute().data or []
    pairs = client.table("language_pairs").select("*").order("source_lang").execute().data or []
    assignments = (
        client.table("translator_languages").select("profile_id,language_pair_id").execute().data or []
    )
    pair_by_id = {p["id"]: p for p in pairs}
    languages_for: dict[str, list[str]] = {}
    for row in assignments:
        pair = pair_by_id.get(row["language_pair_id"])
        if pair is None:
            continue
        languages_for.setdefault(row["profile_id"], []).append(pair_label(pair))

    st.dataframe(
        [
            {
                "name": p["display_name"],
                "email": p["email"],
                "role": p["role"],
                "active": p["is_active"],
                "languages": ", ".join(sorted(languages_for.get(p["id"], []))) or "—",
                "batches": sum(1 for b in batches if b["owner_id"] == p["id"]),
                "annotations": sum(1 for a in anns if a["annotator_id"] == p["id"]),
            }
            for p in profiles
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("##### Invite")
    email = st.text_input("Email")
    name = st.text_input("Display name")
    role = st.selectbox(
        "Role",
        ["translator", "project_manager", "admin"],
        format_func=lambda value: {
            "translator": "Translator",
            "project_manager": "Project Manager",
            "admin": "Admin",
        }[value],
    )
    if st.button("Invite user"):
        try:
            invite_user(email, name, role)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Invited {email}. They can now request an OTP.")
            st.rerun()

    if not profiles:
        return

    pick = st.selectbox("Select user", [f"{p['display_name']} <{p['email']}>" for p in profiles])
    user = next(p for p in profiles if f"{p['display_name']} <{p['email']}>" == pick)

    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("Deactivate"):
        try:
            client.table("profiles").update({"is_active": False}).eq("id", user["id"]).execute()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if c2.button("Activate"):
        client.table("profiles").update({"is_active": True}).eq("id", user["id"]).execute()
        st.rerun()
    if c3.button("Promote to admin"):
        try:
            client.table("profiles").update({"role": "admin"}).eq("id", user["id"]).execute()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if c4.button("Demote to translator"):
        try:
            client.table("profiles").update({"role": "translator"}).eq("id", user["id"]).execute()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if c5.button("Set as project manager"):
        try:
            client.table("profiles").update({"role": "project_manager"}).eq("id", user["id"]).execute()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.markdown("##### Languages")
    st.caption("A volunteer may have several language pairs. Only these pairs can be claimed.")
    if not pairs:
        st.caption("No language pairs yet. Add one under Datasets.")
    else:
        options = [_pair_option(p) for p in pairs]
        option_ids = {_pair_option(p): p["id"] for p in pairs}
        current_ids = {
            row["language_pair_id"]
            for row in assignments
            if row["profile_id"] == user["id"]
        }
        widget_key = f"lang_assign_{user['id']}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = [label for label in options if option_ids[label] in current_ids]
        picked = st.multiselect("Language pairs", options, key=widget_key)
        if st.session_state.pop("languages_saved_for", None) == user["id"]:
            st.success("Languages saved.")
        if st.button("Save languages", key="save_languages"):
            try:
                client.table("translator_languages").delete().eq("profile_id", user["id"]).execute()
                if picked:
                    client.table("translator_languages").insert(
                        [
                            {"profile_id": user["id"], "language_pair_id": option_ids[label]}
                            for label in picked
                        ]
                    ).execute()
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state.languages_saved_for = user["id"]
                st.rerun()

    st.markdown("##### Batches for this user")
    mine = [b for b in batches if b["owner_id"] == user["id"]]
    st.dataframe(mine, hide_index=True, use_container_width=True)
    releasable = [b for b in mine if b["status"] in ("active", "released")]
    if releasable:
        bid = st.selectbox(
            "Batch to release",
            [b["id"] for b in releasable],
            format_func=lambda value: next(
                f"Batch {b['batch_number']} ({b['status']})" for b in releasable if b["id"] == value
            ),
        )
        chosen = next(b for b in releasable if b["id"] == bid)
        r1, r2 = st.columns(2)
        if r1.button("Release batch"):
            try:
                client.rpc("release_batch", {"p_batch_id": bid}).execute()
                st.success("Released. The batch is unclaimed and its annotations were removed.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if chosen["status"] == "active":
            new_owner = st.selectbox(
                "Reassign to",
                ["—"] + [f"{p['display_name']} <{p['email']}>" for p in profiles if p["id"] != user["id"]],
            )
            if r2.button("Reassign") and new_owner != "—":
                target = next(p for p in profiles if f"{p['display_name']} <{p['email']}>" == new_owner)
                try:
                    client.rpc("reassign_batch", {"p_batch_id": bid, "p_new_owner": target["id"]}).execute()
                    st.success("Reassigned.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
