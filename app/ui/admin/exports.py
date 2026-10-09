"""Admin review and CSV export."""

from __future__ import annotations

import streamlit as st

from app.core.exports import (
    EXPORT_COLUMNS,
    fetch_export_rows,
    fetch_iaa_disagreements,
    fetch_suggestions,
    rows_to_csv,
)


def render_exports(client) -> None:
    st.subheader("Review and export")
    pairs = client.table("language_pairs").select("id,source_lang,target_lang").execute().data or []
    datasets = client.table("datasets").select("id,name,version").execute().data or []
    profiles = client.table("profiles").select("id,display_name,email").execute().data or []

    f1, f2, f3 = st.columns(3)
    pair_opt = f1.selectbox("Language pair", ["all"] + [f"{p['source_lang']}→{p['target_lang']}" for p in pairs])
    ds_opt = f2.selectbox("Dataset", ["all"] + [f"{d['name']} v{d['version']}" for d in datasets])
    status = f3.selectbox("Status", ["all", "validated", "rejected", "draft"])
    f4, f5 = st.columns(2)
    who = f4.selectbox("Translator", ["all"] + [p["display_name"] for p in profiles])
    etype = f5.selectbox("Error type", ["all", "Mistranslation", "Addition", "Omission"])

    filters: dict = {}
    if pair_opt != "all":
        filters["language_pair_id"] = next(
            p["id"] for p in pairs if f"{p['source_lang']}→{p['target_lang']}" == pair_opt
        )
    if ds_opt != "all":
        filters["dataset_id"] = next(
            d["id"] for d in datasets if f"{d['name']} v{d['version']}" == ds_opt
        )
    if status != "all":
        filters["status"] = status
    if who != "all":
        filters["annotator_id"] = next(p["id"] for p in profiles if p["display_name"] == who)
    if etype != "all":
        filters["error_type"] = etype

    rows = fetch_export_rows(client, filters=filters)
    st.caption(f"{len(rows)} annotation rows")
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)

    all_rows = fetch_export_rows(client, filters={k: v for k, v in filters.items() if k != "status"})
    validated = [r for r in all_rows if r.get("status") == "validated"]
    rejected = [r for r in all_rows if r.get("status") == "rejected"]
    suggestions = fetch_suggestions(client)
    disagreements = fetch_iaa_disagreements(client)

    st.download_button("All annotations CSV", rows_to_csv(all_rows), "annotations_all.csv", "text/csv")
    st.download_button(
        "Validated only CSV",
        rows_to_csv(validated),
        "annotations_validated.csv",
        "text/csv",
    )
    st.download_button(
        "Rejected / flagged CSV",
        rows_to_csv(rejected),
        "annotations_rejected.csv",
        "text/csv",
    )
    sugg_cols = [
        "suggestion_id",
        "segment_id",
        "batch_id",
        "author_id",
        "author_email",
        "author_name",
        "suggested_text",
        "error_type",
        "severity",
        "notes",
        "created_at",
    ]
    st.download_button(
        "Suggestions CSV",
        rows_to_csv(suggestions, sugg_cols),
        "suggestions.csv",
        "text/csv",
    )
    iaa_cols = [
        "language_pair_id",
        "segment_id",
        "candidate_id",
        "annotator_a",
        "annotator_b",
        "status_a",
        "status_b",
        "status_agree",
        "type_a",
        "type_b",
        "type_agree",
        "sev_a",
        "sev_b",
        "severity_agree",
    ]
    st.download_button(
        "IAA / disagreement CSV",
        rows_to_csv(disagreements, iaa_cols),
        "iaa_disagreements.csv",
        "text/csv",
    )
    st.caption("Exports include IDs, original vs final labels/text, editor, candidate version, timestamps, and status.")
