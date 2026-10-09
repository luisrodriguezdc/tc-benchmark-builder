"""Admin volunteer management."""

from __future__ import annotations

import streamlit as st

from app.core.auth import invite_user


def render_volunteers(client) -> None:
    st.subheader("Volunteers")
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

    st.dataframe(
        [
            {
                "name": p["display_name"],
                "email": p["email"],
                "role": p["role"],
                "active": p["is_active"],
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
    role = st.selectbox("Role", ["translator", "admin"])
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

    c1, c2, c3, c4 = st.columns(4)
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

    st.markdown("##### Batches for this user")
    mine = [b for b in batches if b["owner_id"] == user["id"]]
    st.dataframe(mine, hide_index=True, use_container_width=True)
    active = [b for b in mine if b["status"] == "active"]
    if active:
        bid = st.selectbox("Active batch", [b["id"] for b in active])
        r1, r2 = st.columns(2)
        if r1.button("Release abandoned batch"):
            try:
                client.rpc("release_batch", {"p_batch_id": bid}).execute()
                st.success("Released. Completed annotations were kept.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
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
