"""Production welcome and how-to pages."""

from __future__ import annotations

import html

import streamlit as st

from app.core.auth import Profile
from app.core.constants import HOWTO_DEMO_INTRO, HOWTO_GUIDE, HOWTO_GUIDE_DEMO_SAVE, WELCOME_COPY
from app.core.demo import demo_enabled
from app.ui.components import render_header, render_page_title
from app.ui import styles


def render_welcome(profile: Profile) -> None:
    del profile
    styles.inject()
    render_header()
    render_page_title("Welcome", prominent=True)
    body = WELCOME_COPY
    if demo_enabled():
        body = body.replace(
            "Work is saved to the server. Use Save if a network error appears.",
            HOWTO_GUIDE_DEMO_SAVE,
        )
    st.markdown(_guide_subtitles(body), unsafe_allow_html=True)


_SUBTITLES = {
    "Help Build Better Tools for Translators!",
    "Why are we building a custom benchmark?",
    "How you can help!",
    "How to Use the Interface",
    "Error Types",
    "Error Severity",
    "General Rules",
    "Independence",
}


def _guide_subtitles(body: str) -> str:
    lines = []
    for line in body.splitlines():
        if line.startswith("### "):
            raw = line[4:].strip()
            text = html.escape(raw)
            klass = "tcb-guide-sub" if raw in _SUBTITLES else "tcb-guide-h"
            lines.append(f'<p class="{klass}">{text}</p>')
        else:
            lines.append(line)
    return "\n".join(lines)


def render_howto() -> None:
    styles.inject()
    render_header()
    render_page_title("Annotation Guide", prominent=True)
    body = HOWTO_GUIDE
    if demo_enabled():
        body = HOWTO_DEMO_INTRO + "\n\n" + body
    st.markdown(_guide_subtitles(body), unsafe_allow_html=True)
