"""Screen B — annotation workspace."""

from __future__ import annotations

import uuid

import streamlit as st

from app.core.allocation import set_batch_position
from app.core.annotations import (
    VersionConflict,
    annotation_counts,
    flag_source_error,
    load_workspace,
    save_annotation,
    submit_suggestion,
)
from app.core.auth import Profile
from app.core.constants import ERROR_TYPES, REJECTION_REASONS, SEVERITIES
from app.core.demo import demo_enabled
from app.core.spans import compute_span, parse_tags, region_of, with_tags
from app.ui.components import (
    render_header,
    render_save_status,
    render_segment_banner,
    render_span_preview,
)
from app.ui import styles


def _ensure_card_state(cand: dict, ann: dict | None) -> None:
    cid = cand["id"]
    text_key = f"text_{cid}"
    type_key = f"type_{cid}"
    sev_key = f"sev_{cid}"
    if text_key not in st.session_state:
        st.session_state[text_key] = (ann or {}).get("edited_text") or cand["generated_text"]
    if type_key not in st.session_state:
        st.session_state[type_key] = (ann or {}).get("error_type") or cand["error_type"]
    if sev_key not in st.session_state:
        st.session_state[sev_key] = (ann or {}).get("severity") or cand["severity"]
    st.session_state.setdefault(f"span_start_{cid}", cand.get("target_span_start"))
    st.session_state.setdefault(f"span_end_{cid}", cand.get("target_span_end"))
    st.session_state.setdefault(f"omitted_{cid}", None)
    st.session_state.setdefault(f"insert_at_{cid}", cand.get("target_insert_pos"))
    st.session_state.setdefault(f"omission_custom_{cid}", False)


def _apply_editor(cand: dict, raw: str) -> None:
    cid = cand["id"]
    parsed_text, start, end = parse_tags(raw)
    error_type = st.session_state.get(f"type_{cid}") or cand["error_type"]
    if error_type == "Omission":
        if start is None or end == start:
            st.session_state[f"text_{cid}"] = parsed_text
            st.session_state[f"omitted_{cid}"] = ""
            st.session_state[f"insert_at_{cid}"] = 0
        else:
            st.session_state[f"omitted_{cid}"] = parsed_text[start:end]
            st.session_state[f"insert_at_{cid}"] = start
            st.session_state[f"text_{cid}"] = parsed_text[:start] + parsed_text[end:]
        st.session_state[f"omission_custom_{cid}"] = True
        st.session_state[f"span_start_{cid}"] = None
        st.session_state[f"span_end_{cid}"] = None
    else:
        st.session_state[f"text_{cid}"] = parsed_text
        st.session_state[f"span_start_{cid}"] = start
        st.session_state[f"span_end_{cid}"] = None if end == start else end
        st.session_state[f"omitted_{cid}"] = None
        st.session_state[f"insert_at_{cid}"] = None
        st.session_state[f"omission_custom_{cid}"] = False


def _flush_editor(cand: dict) -> None:
    cid = cand["id"]
    if not st.session_state.get(f"editing_{cid}"):
        return
    raw = st.session_state.get(f"edit_raw_{cid}")
    if isinstance(raw, str):
        _apply_editor(cand, raw)
    st.session_state[f"editing_{cid}"] = False


def _save_card(client, batch_id: str, cand: dict, ann: dict | None, status: str, extra: dict | None = None) -> dict | None:
    cid = cand["id"]
    _flush_editor(cand)
    payload = {
        "candidate_id": cid,
        "batch_id": batch_id,
        "status": status,
        "edited_text": st.session_state[f"text_{cid}"],
        "error_type": st.session_state[f"type_{cid}"],
        "severity": st.session_state[f"sev_{cid}"],
        "rejection_reason": (extra or {}).get("rejection_reason") or (ann or {}).get("rejection_reason"),
        "comment": (extra or {}).get("comment") if extra is not None else (ann or {}).get("comment"),
        "expected_version": int((ann or {}).get("version") or 0),
    }
    if status != "rejected":
        payload["rejection_reason"] = None
    st.session_state.save_status = "saving"
    try:
        saved = save_annotation(client, **payload)
    except VersionConflict:
        st.session_state.save_status = "conflict"
        return None
    except Exception as exc:
        st.session_state.save_status = "failed"
        st.session_state.save_error = str(exc)
        return None
    st.session_state.save_status = "saved"
    st.session_state.setdefault("ann_cache", {})[cid] = saved
    return saved


def _autosave_if_dirty(client, batch_id: str, cand: dict, ann: dict | None) -> None:
    cid = cand["id"]
    if st.session_state.get(f"editing_{cid}"):
        return
    current_text = st.session_state.get(f"text_{cid}")
    current_type = st.session_state.get(f"type_{cid}")
    current_sev = st.session_state.get(f"sev_{cid}")
    baseline_text = (ann or {}).get("edited_text") or cand["generated_text"]
    baseline_type = (ann or {}).get("error_type") or cand["error_type"]
    baseline_sev = (ann or {}).get("severity") or cand["severity"]
    if (current_text, current_type, current_sev) == (baseline_text, baseline_type, baseline_sev):
        return
    status = (ann or {}).get("status") or "draft"
    if status in ("validated", "rejected"):
        status = "draft"
    _save_card(client, batch_id, cand, ann, status)


def render_workspace(client, profile: Profile) -> None:
    styles.inject()
    batch_id = st.session_state.get("batch_id")
    if not batch_id:
        st.session_state.page = "dashboard"
        st.rerun()

    try:
        data = load_workspace(client, batch_id, profile.id)
    except Exception as exc:
        st.error(f"Could not load batch: {exc}")
        if st.button("← Batches"):
            st.session_state.page = "dashboard"
            st.rerun()
        return

    batch = data["batch"]
    items = data["items"]
    lp = batch.get("language_pairs") or {}
    render_header()

    if st.button("← Batches"):
        st.session_state.page = "dashboard"
        st.rerun()
    st.caption(
        f"Target: {lp.get('target_label') or lp.get('target_lang')} · Batch #{batch.get('batch_number')}"
    )

    if not items:
        st.warning("This batch has no segments.")
        return

    counts = annotation_counts(items)
    st.markdown(
        f'<p class="tcb-counts">Validated {counts["validated"]} · Rejected {counts["rejected"]} · Incomplete {counts["incomplete"]}</p>',
        unsafe_allow_html=True,
    )
    render_save_status(st.session_state.get("save_status", ""))
    if st.session_state.get("save_status") == "failed" and st.session_state.get("save_error"):
        st.error(st.session_state.save_error)

    pos = int(st.session_state.get("ws_pos") or batch.get("last_position") or 1)
    pos = min(max(pos, 1), len(items))
    st.session_state.ws_pos = pos
    current = items[pos - 1]
    segment = current["segment"] or {}
    item = current.get("item") or {}
    flagged = bool(item.get("source_error"))
    if render_segment_banner(
        pos,
        len(items),
        segment.get("source_text", ""),
        segment.get("reference_text", ""),
        flagged=flagged,
        flag_key=f"src_err_{segment.get('id') or pos}",
    ):
        try:
            flag_source_error(
                client,
                batch_id=batch_id,
                segment_id=segment["id"],
                flagged=not flagged,
            )
        except Exception as exc:
            st.session_state.save_status = "failed"
            st.session_state.save_error = str(exc)
        else:
            item["source_error"] = not flagged
        st.rerun()

    cache = st.session_state.setdefault("ann_cache", {})
    cands = current["candidates"]
    if flagged:
        st.markdown(
            '<p class="status-validated">This segment does not need validation — source/reference flagged as invalid.</p>',
            unsafe_allow_html=True,
        )
    elif cands and all(
        ((cache.get(c["id"]) or current["annotations"].get(c["id"]) or {}).get("status") in ("validated", "rejected"))
        for c in cands
    ):
        st.markdown('<p class="status-validated">This segment is resolved.</p>', unsafe_allow_html=True)
    if batch.get("status") == "completed":
        st.markdown(
            '<div class="tcb-alert ok">This batch is complete. Every generated candidate is validated or rejected. Suggestions were optional.</div>',
            unsafe_allow_html=True,
        )

    for cand in cands:
        ann = cache.get(cand["id"]) or current["annotations"].get(cand["id"])
        current["annotations"][cand["id"]] = ann
        _ensure_card_state(cand, ann)
        _render_card(client, batch_id, segment, cand, ann, source_invalid=flagged)
        _autosave_if_dirty(client, batch_id, cand, current["annotations"].get(cand["id"]))

    _render_suggestions(client, batch_id, segment, current.get("suggestions") or [])

    nav_l, nav_r = st.columns(2)
    with nav_l:
        if st.button("← Back", disabled=pos <= 1, width="stretch"):
            _flush_segment(client, batch_id, current)
            st.session_state.ws_pos = pos - 1
            set_batch_position(client, batch_id, pos - 1)
            st.rerun()
    with nav_r:
        if st.button("Next →", disabled=pos >= len(items), width="stretch"):
            _flush_segment(client, batch_id, current)
            st.session_state.ws_pos = pos + 1
            set_batch_position(client, batch_id, pos + 1)
            st.rerun()


def _flush_segment(client, batch_id: str, current: dict) -> None:
    for cand in current["candidates"]:
        _flush_editor(cand)
        ann = current["annotations"].get(cand["id"])
        _autosave_if_dirty(client, batch_id, cand, ann)


def _region_kwargs(cand: dict, segment: dict) -> dict:
    cid = cand["id"]
    return dict(
        error_type=st.session_state.get(f"type_{cid}") or cand["error_type"],
        generated_text=cand["generated_text"],
        edited_text=st.session_state.get(f"text_{cid}") or cand["generated_text"],
        reference_text=segment.get("reference_text") or "",
        target_span_start=cand.get("target_span_start"),
        target_span_end=cand.get("target_span_end"),
        ref_span_start=cand.get("ref_span_start"),
        ref_span_end=cand.get("ref_span_end"),
        target_insert_pos=cand.get("target_insert_pos"),
        omitted_text=st.session_state.get(f"omitted_{cid}"),
        insert_at=st.session_state.get(f"insert_at_{cid}"),
        span_start=st.session_state.get(f"span_start_{cid}"),
        span_end=st.session_state.get(f"span_end_{cid}"),
        has_custom_omission=bool(st.session_state.get(f"omission_custom_{cid}")),
    )


def _pill_selectbox(label: str, options: tuple[str, ...], key: str, kind: str, disabled: bool) -> None:
    value = st.session_state.get(key)
    if kind == "severity":
        mark = "tcb-mark-minor" if value == "Minor" else "tcb-mark-major"
    else:
        mark = "tcb-mark-type"
    st.markdown(f'<div class="{mark}"></div>', unsafe_allow_html=True)
    st.selectbox(label, options, key=key, disabled=disabled, label_visibility="collapsed")


def _render_card(
    client,
    batch_id: str,
    segment: dict,
    cand: dict,
    ann: dict | None,
    *,
    source_invalid: bool = False,
) -> None:
    cid = cand["id"]
    status = (ann or {}).get("status") or "draft"
    locked = status in ("validated", "rejected") and not st.session_state.get(f"reopen_{cid}")
    editing = bool(st.session_state.get(f"editing_{cid}")) and not locked
    with st.container(border=True):
        top = st.columns([1.5, 2.25, 5.2, 1.05, 0.52], gap="small", vertical_alignment="center")
        with top[0]:
            _pill_selectbox("Severity", SEVERITIES, f"sev_{cid}", "severity", locked)
        with top[1]:
            _pill_selectbox("Error type", ERROR_TYPES, f"type_{cid}", "type", locked)
        with top[3]:
            if editing:
                if st.button("Save", key=f"saveedit_{cid}", type="primary", width="stretch"):
                    _flush_editor(cand)
                    _save_card(client, batch_id, cand, ann, (ann or {}).get("status") or "draft")
                    st.rerun()
            elif st.button("Edit", key=f"edit_{cid}", disabled=locked, width="stretch"):
                region = region_of(**_region_kwargs(cand, segment))
                st.session_state[f"edit_raw_{cid}"] = with_tags(region.text, region.start, region.end)
                st.session_state[f"editing_{cid}"] = True
                st.rerun()
        with top[4]:
            reject_click = st.button("×", key=f"rejbtn_{cid}", disabled=locked, width="stretch")

        if editing:
            st.text_area(
                "Edit target. Angle brackets mark the error region.",
                key=f"edit_raw_{cid}",
                height=90,
                label_visibility="collapsed",
            )
            et = st.session_state.get(f"type_{cid}") or cand["error_type"]
            if et == "Omission":
                st.caption("Text inside <> is the omitted span. It is shown with a strikethrough and is not part of the sentence.")
            else:
                st.caption("Angle brackets mark the error region. They are not part of the sentence.")
        else:
            render_span_preview(**_region_kwargs(cand, segment))

        foot_l, foot_r = st.columns([3.8, 2.4] if source_invalid else [5, 1.6])
        with foot_r:
            if source_invalid:
                st.button("Invalid source", key=f"invalid_{cid}", disabled=True, width="stretch")
            elif locked:
                if st.button("Reopen", key=f"reopenbtn_{cid}", width="stretch"):
                    saved = _save_card(client, batch_id, cand, ann, "draft")
                    if saved is not None:
                        st.session_state[f"reopen_{cid}"] = True
                    st.rerun()
            else:
                if st.button("Validate ✓", key=f"val_{cid}", type="primary", width="stretch"):
                    saved = _save_card(client, batch_id, cand, ann, "validated")
                    if saved is not None:
                        st.session_state.pop(f"reopen_{cid}", None)
                    st.rerun()

        if reject_click:
            st.session_state[f"rejecting_{cid}"] = True
        if st.session_state.get(f"rejecting_{cid}") and not locked:
            reason = st.selectbox(
                "Rejection reason",
                [r[0] for r in REJECTION_REASONS],
                format_func=lambda k: dict(REJECTION_REASONS)[k],
                key=f"rej_reason_{cid}",
            )
            comment = st.text_input("Comment (optional)", key=f"rej_comment_{cid}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirm reject", key=f"rej_confirm_{cid}", type="primary"):
                    saved = _save_card(
                        client,
                        batch_id,
                        cand,
                        ann,
                        "rejected",
                        extra={"rejection_reason": reason, "comment": comment or None},
                    )
                    if saved is not None:
                        st.session_state[f"rejecting_{cid}"] = False
                        st.session_state.pop(f"reopen_{cid}", None)
                    st.rerun()
            with c2:
                if st.button("Cancel", key=f"rej_cancel_{cid}"):
                    st.session_state[f"rejecting_{cid}"] = False
                    st.rerun()
        if status == "rejected" and (ann or {}).get("rejection_reason"):
            label = dict(REJECTION_REASONS).get(ann["rejection_reason"], ann["rejection_reason"])
            st.caption(f"Rejection: {label}")


def _norm_sentence(text: str) -> str:
    return " ".join((text or "").split())


def _sentence_from_raw(raw: str, error_type: str) -> str:
    parsed, start, end = parse_tags(raw or "")
    if error_type == "Omission" and start is not None and end != start:
        return parsed[:start] + parsed[end:]
    return parsed


def _sugg_draft_ids(segment_id: str) -> list[str]:
    store = st.session_state.setdefault("sugg_drafts", {})
    return store.setdefault(segment_id, [])


def _drop_sugg_draft(segment_id: str, did: str) -> None:
    ids = _sugg_draft_ids(segment_id)
    if did in ids:
        ids.remove(did)
    for prefix in ("sugg_raw_", "sugg_type_", "sugg_sev_", "sugg_err_"):
        st.session_state.pop(f"{prefix}{did}", None)


def _render_suggestions(client, batch_id: str, segment: dict, existing: list[dict]) -> None:
    seg_id = segment.get("id") or ""
    reference = segment.get("reference_text") or ""
    for saved in existing:
        _render_saved_suggestion(saved, reference)
    for did in list(_sugg_draft_ids(seg_id)):
        _render_draft_suggestion(client, batch_id, segment, did)

    _, btn, _ = st.columns([1, 2.2, 1])
    with btn:
        if st.button("Suggest an additional error", key=f"add_sugg_{seg_id}", width="stretch"):
            did = uuid.uuid4().hex[:10]
            _sugg_draft_ids(seg_id).append(did)
            st.session_state[f"sugg_raw_{did}"] = reference
            st.session_state[f"sugg_type_{did}"] = ERROR_TYPES[0]
            st.session_state[f"sugg_sev_{did}"] = SEVERITIES[0]
            st.rerun()


def _render_saved_suggestion(saved: dict, reference: str) -> None:
    sid = saved.get("id") or uuid.uuid4().hex[:8]
    etype = saved.get("error_type") or ERROR_TYPES[0]
    sev = saved.get("severity") or SEVERITIES[0]
    text = saved.get("suggested_text") or ""
    st.session_state[f"sugg_saved_type_{sid}"] = etype
    st.session_state[f"sugg_saved_sev_{sid}"] = sev
    with st.container(border=True):
        top = st.columns([1.5, 2.25, 6.77], gap="small", vertical_alignment="center")
        with top[0]:
            _pill_selectbox("Severity", SEVERITIES, f"sugg_saved_sev_{sid}", "severity", True)
        with top[1]:
            _pill_selectbox("Error type", ERROR_TYPES, f"sugg_saved_type_{sid}", "type", True)
        span = compute_span(reference, text, etype)
        render_span_preview(
            error_type=etype,
            generated_text=text,
            edited_text=text,
            reference_text=reference,
            target_span_start=span.target_start,
            target_span_end=span.target_end,
            ref_span_start=span.ref_start,
            ref_span_end=span.ref_end,
            target_insert_pos=span.target_insert_pos,
        )


def _render_draft_suggestion(client, batch_id: str, segment: dict, did: str) -> None:
    seg_id = segment.get("id") or ""
    reference = segment.get("reference_text") or ""
    st.session_state.setdefault(f"sugg_raw_{did}", reference)
    st.session_state.setdefault(f"sugg_type_{did}", ERROR_TYPES[0])
    st.session_state.setdefault(f"sugg_sev_{did}", SEVERITIES[0])
    with st.container(border=True):
        top = st.columns([1.5, 2.25, 5.2, 1.05, 0.52], gap="small", vertical_alignment="center")
        with top[0]:
            _pill_selectbox("Severity", SEVERITIES, f"sugg_sev_{did}", "severity", False)
        with top[1]:
            _pill_selectbox("Error type", ERROR_TYPES, f"sugg_type_{did}", "type", False)
        with top[3]:
            save_click = st.button("Save", key=f"sugg_save_{did}", type="primary", width="stretch")
        with top[4]:
            dismiss = st.button("×", key=f"sugg_drop_{did}", width="stretch")

        st.text_area(
            "Edit target. Angle brackets mark the error region.",
            key=f"sugg_raw_{did}",
            height=90,
            label_visibility="collapsed",
        )
        et = st.session_state.get(f"sugg_type_{did}") or ERROR_TYPES[0]
        if et == "Omission":
            st.caption("Text inside <> is the omitted span. It is shown with a strikethrough and is not part of the sentence.")
        else:
            st.caption("Angle brackets mark the error region. They are not part of the sentence.")

        err = st.session_state.get(f"sugg_err_{did}")
        if err:
            st.warning(err)

        if dismiss:
            _drop_sugg_draft(seg_id, did)
            st.rerun()

        if save_click:
            raw = st.session_state.get(f"sugg_raw_{did}") or ""
            sentence = _sentence_from_raw(raw, et)
            if not sentence.strip():
                st.session_state[f"sugg_err_{did}"] = "Enter a suggested target sentence."
                st.rerun()
            if _norm_sentence(sentence) == _norm_sentence(reference):
                st.session_state[f"sugg_err_{did}"] = (
                    "The suggested target must differ from the reference."
                )
                st.rerun()
            try:
                submit_suggestion(
                    client,
                    segment_id=seg_id,
                    batch_id=batch_id,
                    suggested_text=sentence,
                    error_type=et,
                    severity=st.session_state.get(f"sugg_sev_{did}") or SEVERITIES[0],
                    notes=None,
                )
            except Exception as exc:
                st.session_state[f"sugg_err_{did}"] = str(exc)
                st.rerun()
            _drop_sugg_draft(seg_id, did)
            st.rerun()
