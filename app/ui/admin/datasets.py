"""Admin dataset and language-pair management."""

from __future__ import annotations

import streamlit as st

from app.core.allocation import pair_label
from app.core.importer import parse_csv, persist_import
from app.core.store import SupabaseStore


def render_datasets(client) -> None:
    st.subheader("Datasets")
    store = SupabaseStore(client)

    st.markdown("##### Language pairs")
    pairs = client.table("language_pairs").select("*").order("source_lang").execute().data or []
    st.dataframe(
        [
            {
                "id": p["id"],
                "pair": pair_label(p),
                "codes": f"{p['source_lang']}→{p['target_lang']}",
                "IAA %": p["iaa_target_pct"],
                "Batch size": p["batch_size"],
                "Active": p["is_active"],
            }
            for p in pairs
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("Add or update a language pair"):
        c1, c2, c3, c4 = st.columns(4)
        src = c1.text_input("Source code", value="en")
        tgt = c2.text_input("Target code", placeholder="fr")
        src_l = c3.text_input("Source label", value="English")
        tgt_l = c4.text_input("Target label", placeholder="French")
        iaa = st.number_input("IAA target %", min_value=0.0, max_value=100.0, value=15.0)
        bsize = st.number_input("Batch size", min_value=1, value=100)
        if st.button("Save language pair"):
            if not tgt.strip():
                st.error("Target code is required.")
            else:
                existing = store.find_language_pair(src.strip(), tgt.strip())
                if existing:
                    client.table("language_pairs").update(
                        {
                            "source_label": src_l,
                            "target_label": tgt_l,
                            "iaa_target_pct": iaa,
                            "batch_size": int(bsize),
                            "is_active": True,
                        }
                    ).eq("id", existing["id"]).execute()
                    st.success("Updated existing pair.")
                else:
                    store.insert_language_pair(
                        {
                            "source_lang": src.strip(),
                            "target_lang": tgt.strip(),
                            "source_label": src_l,
                            "target_label": tgt_l,
                            "iaa_target_pct": iaa,
                            "batch_size": int(bsize),
                            "is_active": True,
                        }
                    )
                    st.success("Created language pair.")
                st.rerun()

    deactivate = st.selectbox(
        "Deactivate pair",
        ["—"] + [f"{pair_label(p)} ({p['id'][:8]})" for p in pairs if p["is_active"]],
    )
    if deactivate != "—" and st.button("Deactivate"):
        pid = next(p["id"] for p in pairs if p["id"][:8] in deactivate)
        client.table("language_pairs").update({"is_active": False}).eq("id", pid).execute()
        st.rerun()

    st.markdown("##### Import CSV")
    st.caption("Preview first, then publish. Assigned published candidates are versioned, never overwritten.")
    uploaded = st.file_uploader("CSV file", type=["csv"])
    publish = st.checkbox("Publish immediately after import", value=False)
    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8-sig")
        try:
            rows = parse_csv(text)
        except Exception as exc:
            st.error(f"Could not parse CSV: {exc}")
            rows = []
        if rows:
            st.write(f"{len(rows)} candidate rows, {len({r.external_segment_id for r in rows})} segments.")
            st.dataframe(
                [
                    {
                        "segment": r.external_segment_id,
                        "candidate": r.candidate_id,
                        "type": r.error_type,
                        "severity": r.severity,
                        "target": r.generated_target[:80],
                    }
                    for r in rows[:30]
                ],
                hide_index=True,
                use_container_width=True,
            )
            if st.button("Import"):
                report = persist_import(store, rows, publish=publish, create_missing_pairs=True)
                st.success(
                    f"Datasets {report.datasets_upserted}, segments {report.segments_upserted}, "
                    f"inserted {report.candidates_inserted}, updated {report.candidates_updated}, "
                    f"versioned {report.candidates_versioned}, skipped {report.candidates_skipped}."
                )
                if report.errors:
                    st.warning("\n".join(report.errors))
                try:
                    client.rpc(
                        "write_audit",
                        {
                            "p_action": "import_csv",
                            "p_entity": "datasets",
                            "p_entity_id": None,
                            "p_details": {
                                "inserted": report.candidates_inserted,
                                "versioned": report.candidates_versioned,
                                "publish": publish,
                            },
                        },
                    ).execute()
                except Exception:
                    pass

    st.markdown("##### Existing datasets")
    datasets = (
        client.table("datasets")
        .select("*, language_pairs(source_lang,target_lang,source_label,target_label)")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    st.dataframe(
        [
            {
                "name": d["name"],
                "version": d["version"],
                "status": d["status"],
                "pair": pair_label(d.get("language_pairs") or {}),
                "id": d["id"],
            }
            for d in datasets
        ],
        hide_index=True,
        use_container_width=True,
    )

    if datasets:
        labels = {f"{d['name']} v{d['version']} ({d['status']})": d for d in datasets}
        pick = st.selectbox("Dataset actions", list(labels.keys()))
        ds = labels[pick]
        b1, b2, b3 = st.columns(3)
        if b1.button("Publish"):
            client.table("datasets").update({"status": "published"}).eq("id", ds["id"]).execute()
            segs = client.table("segments").select("id").eq("dataset_id", ds["id"]).execute().data or []
            for s in segs:
                client.table("error_candidates").update({"status": "published"}).eq(
                    "segment_id", s["id"]
                ).eq("status", "draft").execute()
            st.success("Published.")
            st.rerun()
        if b2.button("Archive (keeps annotations)"):
            client.table("datasets").update({"status": "archived"}).eq("id", ds["id"]).execute()
            segs = client.table("segments").select("id").eq("dataset_id", ds["id"]).execute().data or []
            for s in segs:
                client.table("error_candidates").update({"status": "archived"}).eq(
                    "segment_id", s["id"]
                ).execute()
            st.success("Archived.")
            st.rerun()

        st.markdown("##### Draft candidates in this dataset (unassigned)")
        segs = client.table("segments").select("id,external_id").eq("dataset_id", ds["id"]).execute().data or []
        seg_ids = [s["id"] for s in segs]
        if seg_ids:
            cands = (
                client.table("error_candidates")
                .select("*")
                .in_("segment_id", seg_ids)
                .eq("status", "draft")
                .limit(50)
                .execute()
                .data
                or []
            )
            st.dataframe(
                [
                    {
                        "external_id": c["external_id"],
                        "type": c["error_type"],
                        "severity": c["severity"],
                        "text": c["generated_text"][:80],
                        "version": c["version"],
                    }
                    for c in cands
                ],
                hide_index=True,
                use_container_width=True,
            )
