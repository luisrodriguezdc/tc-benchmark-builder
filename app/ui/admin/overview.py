"""Admin overview + IAA coverage."""

from __future__ import annotations

import streamlit as st

from app.core.allocation import pair_label


def render_overview(client) -> None:
    st.subheader("Overview")
    pairs = client.table("language_pairs").select("*").execute().data or []
    datasets = client.table("datasets").select("*").execute().data or []
    segments = client.table("segments").select("id,dataset_id").execute().data or []
    candidates = client.table("error_candidates").select("id,status,error_type").execute().data or []
    batches = client.table("batches").select("*").execute().data or []
    anns = client.table("annotations").select("status,annotator_id").execute().data or []
    suggestions = client.table("error_suggestions").select("id").execute().data or []
    profiles = client.table("profiles").select("id,display_name,email,role,is_active").execute().data or []
    iaa = client.table("iaa_pair_stats").select("*").execute().data or []

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Language pairs", len(pairs))
    c2.metric("Segments", len(segments))
    c3.metric("Candidates", len(candidates))
    c4.metric("Suggestions", len(suggestions))

    st.markdown("##### By language pair")
    ds_by_pair = {}
    for d in datasets:
        ds_by_pair.setdefault(d["language_pair_id"], []).append(d["id"])
    seg_by_ds = {}
    for s in segments:
        seg_by_ds.setdefault(s["dataset_id"], 0)
        seg_by_ds[s["dataset_id"]] += 1

    rows = []
    for p in pairs:
        ds_ids = ds_by_pair.get(p["id"], [])
        n_seg = sum(seg_by_ds.get(i, 0) for i in ds_ids)
        n_batch = sum(1 for b in batches if b["language_pair_id"] == p["id"])
        iaa_row = next((x for x in iaa if x["language_pair_id"] == p["id"]), {})
        rows.append(
            {
                "Pair": pair_label(p),
                "Active": p["is_active"],
                "Segments": n_seg,
                "Batches": n_batch,
                "IAA target %": p["iaa_target_pct"],
                "Coverage %": iaa_row.get("coverage_pct"),
                "≥1 annotator": iaa_row.get("unique_with_one"),
                "≥2 annotators": iaa_row.get("unique_with_two"),
                "IAA target count": iaa_row.get("iaa_target_count"),
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)

    st.markdown("##### Annotations")
    a1, a2, a3 = st.columns(3)
    a1.metric("Validated", sum(1 for a in anns if a["status"] == "validated"))
    a2.metric("Rejected", sum(1 for a in anns if a["status"] == "rejected"))
    a3.metric("Draft", sum(1 for a in anns if a["status"] == "draft"))

    st.markdown("##### Translator progress")
    trows = []
    for p in profiles:
        mine = [a for a in anns if a["annotator_id"] == p["id"]]
        trows.append(
            {
                "Name": p["display_name"],
                "Role": p["role"],
                "Active": p["is_active"],
                "Annotations": len(mine),
                "Validated": sum(1 for a in mine if a["status"] == "validated"),
                "Rejected": sum(1 for a in mine if a["status"] == "rejected"),
                "Batches": sum(1 for b in batches if b["owner_id"] == p["id"]),
            }
        )
    st.dataframe(trows, hide_index=True, use_container_width=True)

    st.markdown("##### IAA coverage")
    st.caption("Edited target texts are preserved independently and are not treated as disagreements.")
    if iaa:
        st.dataframe(iaa, hide_index=True, use_container_width=True)
    try:
        agreements = client.table("iaa_agreements").select("*").limit(500).execute().data or []
    except Exception:
        agreements = []
    if agreements:
        n = len(agreements)
        status_agree = sum(1 for r in agreements if r.get("status_agree"))
        type_comp = [r for r in agreements if r.get("status_a") == "validated" and r.get("status_b") == "validated"]
        st.write(
            f"Paired candidate comparisons: {n}. "
            f"Status agreement: {status_agree}/{n}. "
            f"Type agreement on dual-validated: "
            f"{sum(1 for r in type_comp if r.get('type_agree'))}/{len(type_comp)}."
        )
