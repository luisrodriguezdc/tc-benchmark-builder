"""Shared Streamlit chrome: header, how-to, span preview, save status."""

from __future__ import annotations

import html

import streamlit as st

from app.core.auth import Profile
from app.core.constants import APP_TITLE
from app.core.demo import demo_enabled
from app.core.spans import region_of, render_highlighted_html

NAV_EMOJI = {
    "Welcome": "👋",
    "Annotation Guide": "📖",
    "Workspace": "✏️",
    "Dashboard": "📊",
    "Datasets": "📁",
    "Volunteers": "👥",
    "Review & export": "📤",
}


def render_sidebar_nav(options: list[str]) -> str:
    """Vertical nav. The selected row is a rounded light-gray bar, with no radio control."""
    if st.session_state.get("prod_nav") not in options:
        st.session_state.prod_nav = "Workspace"
    choice = st.session_state.prod_nav
    with st.sidebar:
        st.markdown(
            f'<p class="tcb-sidebar-title">{html.escape(APP_TITLE)}</p>',
            unsafe_allow_html=True,
        )
        nav = st.container(gap="xxsmall", border=False)
        for label in options:
            slug = label.lower().replace(" & ", "_").replace(" ", "_")
            if nav.button(
                label,
                key=f"navbtn_{slug}",
                icon=NAV_EMOJI[label],
                type="primary" if label == choice else "tertiary",
                width="stretch",
            ):
                if label != choice:
                    st.session_state.prod_nav = label
                    st.rerun()
    return choice


def render_page_title(title: str, *, admin: bool = False, prominent: bool = False) -> None:
    chip = '<span class="tcb-admin-chip">Admin</span>' if admin else ""
    gap = " " if admin else ""
    klass = "tcb-title tcb-title-prominent" if prominent else "tcb-title"
    st.markdown(
        f'<div class="{klass}">{html.escape(title)}{gap}{chip}</div>',
        unsafe_allow_html=True,
    )


def _logout() -> None:
    if not demo_enabled():
        client = st.session_state.get("client")
        if client is not None:
            try:
                client.auth.sign_out({"scope": "local"})
            except Exception:
                pass
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if not demo_enabled():
        st.session_state.clear_auth_cookies = True
    st.rerun()


def render_account_menu(profile: Profile) -> None:
    with st.sidebar:
        with st.container(key="account_dock"):
            with st.popover(profile.display_name, icon=":material/account_circle:"):
                st.caption(profile.email)
                if st.button("Log out", key="logout", width="stretch"):
                    _logout()


def render_header() -> None:
    if not demo_enabled():
        return
    st.markdown(
        '<div class="tcb-brand"><span class="tcb-badge">Demo</span></div>',
        unsafe_allow_html=True,
    )


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
