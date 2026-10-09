"""Shared Streamlit chrome: header, how-to, span preview, save status."""

from __future__ import annotations

import streamlit as st

from app.core.auth import Profile, cookie_clear_js
from app.core.constants import APP_TITLE, HOWTO_DEMO_INTRO, HOWTO_GUIDE, HOWTO_GUIDE_DEMO_SAVE
from app.core.demo import demo_enabled
from app.core.spans import region_of, render_highlighted_html


def _howto_markdown() -> str:
    if not demo_enabled():
        return HOWTO_GUIDE
    body = HOWTO_GUIDE.replace(
        "Work is saved to the server. Use **Save** if a network error appears.",
        HOWTO_GUIDE_DEMO_SAVE,
    )
    return HOWTO_DEMO_INTRO + "\n\n" + body


def _logout() -> None:
    st.components.v1.html(cookie_clear_js(), height=0)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def render_account_menu(profile: Profile) -> None:
    with st.sidebar:
        with st.popover(profile.display_name, icon=":material/account_circle:"):
            st.caption(profile.email)
            if st.button("Log out", key="logout", width="stretch"):
                _logout()


def render_header() -> None:
    badge = ' <span class="tcb-badge">Demo</span>' if demo_enabled() else ""
    st.markdown(
        f'<div class="tcb-brand"><span class="tcb-title">{APP_TITLE}</span>{badge}</div>',
        unsafe_allow_html=True,
    )
    with st.expander("How To Guide", expanded=False):
        st.markdown(_howto_markdown())


def render_segment_banner(
    position: int,
    total: int,
    source: str,
    reference: str,
    *,
    flagged: bool = False,
    flag_key: str = "src_err",
) -> bool:
    marker = "tcb-banner-marker flagged" if flagged else "tcb-banner-marker"
    st.markdown(f'<div class="{marker}"></div>', unsafe_allow_html=True)
    if flagged:
        clicked = st.button("Undo", key=f"{flag_key}_undo", help="Clear the source/reference error flag")
    else:
        clicked = st.button(
            "×",
            key=f"{flag_key}_x",
            help="Mark that the source or reference already contains an error",
        )
    flag_note = (
        '<div class="flag-note">Source/reference flagged — existing error</div>' if flagged else ""
    )
    flagged_cls = " flagged" if flagged else ""
    st.markdown(
        f"""
<div class="segment-banner{flagged_cls}">
  <div class="progress">Segment {position} / {total}</div>
  <div class="k">Source</div>
  <div class="line">{_escape(source)}</div>
  <div class="k">Reference</div>
  <div class="line">{_escape(reference)}</div>
  {flag_note}
</div>
""",
        unsafe_allow_html=True,
    )
    return clicked


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
    omitted_text: str | None = None,
    insert_at: int | None = None,
    span_start: int | None = None,
    span_end: int | None = None,
    has_custom_omission: bool = False,
) -> None:
    region = region_of(
        error_type=error_type,
        generated_text=generated_text,
        edited_text=edited_text,
        reference_text=reference_text,
        target_span_start=target_span_start,
        target_span_end=target_span_end,
        ref_span_start=ref_span_start,
        ref_span_end=ref_span_end,
        target_insert_pos=target_insert_pos,
        omitted_text=omitted_text,
        insert_at=insert_at,
        span_start=span_start,
        span_end=span_end,
        has_custom_omission=has_custom_omission,
    )
    html_tgt = render_highlighted_html(
        region.text,
        region.start,
        region.end,
        approximate=region.approximate,
        strike=region.strike,
    )
    st.markdown(f'<div class="span-preview">{html_tgt}</div>', unsafe_allow_html=True)
    if region.start is None and edited_text != generated_text and not region.strike:
        st.markdown(
            '<div class="span-note">Highlight unavailable after the edit (original span metadata was kept).</div>',
            unsafe_allow_html=True,
        )
    elif region.approximate:
        st.markdown(
            '<div class="span-note">Approximate highlight after editing — original offsets were preserved.</div>',
            unsafe_allow_html=True,
        )


def render_save_status(status: str) -> None:
    if status == "saving":
        st.markdown('<div class="save-busy">Saving…</div>', unsafe_allow_html=True)
    elif status == "saved":
        msg = (
            "Saved in this browser only. The live database is unchanged."
            if demo_enabled()
            else "Saved"
        )
        st.markdown(f'<div class="save-ok">{msg}</div>', unsafe_allow_html=True)
    elif status == "failed":
        st.markdown('<div class="save-fail">Save failed — retry or use Save.</div>', unsafe_allow_html=True)
    elif status == "conflict":
        st.markdown(
            '<div class="save-fail">Version conflict — another session saved first. Reloaded server copy.</div>',
            unsafe_allow_html=True,
        )
