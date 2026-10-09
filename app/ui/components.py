"""Shared Streamlit chrome: header, how-to, span preview, save status."""

from __future__ import annotations

import streamlit as st

from app.core.auth import Profile, cookie_clear_js
from app.core.constants import APP_TITLE, HOWTO_GUIDE
from app.core.spans import realign_span, render_highlighted_html


def render_header(profile: Profile, extra: str | None = None) -> None:
    left, right = st.columns([3, 1.1])
    with left:
        st.markdown(f'<div class="tcb-title">{APP_TITLE}</div>', unsafe_allow_html=True)
        with st.expander("How To Guide", expanded=False):
            st.markdown(HOWTO_GUIDE)
    with right:
        bits = [f"{profile.display_name}", profile.role]
        if extra:
            bits.insert(0, extra)
        st.markdown(
            '<div class="tcb-userbox">' + "<br>".join(bits) + "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Logout →", key="logout"):
            st.components.v1.html(cookie_clear_js(), height=0)
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def render_segment_banner(position: int, total: int, source: str, reference: str) -> None:
    st.markdown(
        f"""
<div class="segment-banner">
  <div class="progress">Segment {position} / {total}</div>
  <div class="src">{_escape(source)}</div>
  <div class="ref">{_escape(reference)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _escape(text: str) -> str:
    import html

    return html.escape(text or "")


def render_span_preview(
    *,
    error_type: str,
    generated_text: str,
    edited_text: str,
    reference_text: str,
    target_span_start: int | None,
    target_span_end: int | None,
    ref_span_start: int | None,
    ref_span_end: int | None,
    target_insert_pos: int | None,
) -> None:
    approximate = False
    if error_type == "Omission":
        html_ref = render_highlighted_html(reference_text, ref_span_start, ref_span_end)
        note = ""
        if target_insert_pos is not None:
            note = f" Insertion position in the candidate (character {target_insert_pos})."
        st.markdown(
            f'<div class="span-preview"><em>Reference:</em> {html_ref}</div>',
            unsafe_allow_html=True,
        )
        if note:
            st.caption(note)
        if edited_text != generated_text:
            st.markdown(
                '<div class="span-note">Omission has no forced span in the edited target.</div>',
                unsafe_allow_html=True,
            )
        return

    start, end = target_span_start, target_span_end
    if edited_text != generated_text:
        start, end, approximate = realign_span(generated_text, target_span_start, target_span_end, edited_text)
        if start is None:
            st.markdown(f'<div class="span-preview">{_escape(edited_text)}</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="span-note">Highlight unavailable after the edit (original span metadata was kept).</div>',
                unsafe_allow_html=True,
            )
            return
    html_tgt = render_highlighted_html(edited_text, start, end, approximate=approximate)
    st.markdown(f'<div class="span-preview">{html_tgt}</div>', unsafe_allow_html=True)
    if approximate:
        st.markdown(
            '<div class="span-note">Approximate highlight after editing — original offsets were preserved.</div>',
            unsafe_allow_html=True,
        )


def render_save_status(status: str) -> None:
    if status == "saving":
        st.markdown('<div class="save-busy">Saving…</div>', unsafe_allow_html=True)
    elif status == "saved":
        st.markdown('<div class="save-ok">Saved</div>', unsafe_allow_html=True)
    elif status == "failed":
        st.markdown('<div class="save-fail">Save failed — retry or use Save.</div>', unsafe_allow_html=True)
    elif status == "conflict":
        st.markdown(
            '<div class="save-fail">Version conflict — another session saved first. Reloaded server copy.</div>',
            unsafe_allow_html=True,
        )
