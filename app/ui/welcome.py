"""Production welcome and how-to pages."""

from __future__ import annotations

import streamlit as st

from app.core.auth import Profile
from app.core.constants import HOWTO_GUIDE
from app.ui.components import render_header
from app.ui import styles


def render_welcome(profile: Profile) -> None:
    styles.inject()
    render_header()
    name = profile.display_name or profile.email
    st.markdown('<div class="tcb-title">Welcome</div>', unsafe_allow_html=True)
    st.markdown(f"Hello, **{name}**.")
    st.markdown(
        "This workspace is where Translation Commons linguists check synthetic "
        "translation errors. Each card should contain exactly one intended error."
    )
    st.markdown(
        """
1. Open **How To Guide** for the validate, edit, and reject rules.
2. Open **Dashboard** to see every language batch and its status.
3. **Claim This Batch** is shown for languages an admin assigned to you. You can hold one active batch at a time.
        """.strip()
    )
    if profile.is_admin:
        st.caption("This account is an admin. Dataset, volunteer, and export pages are in the left navigation.")


def render_howto() -> None:
    styles.inject()
    render_header()
    st.markdown('<div class="tcb-title">How To Guide</div>', unsafe_allow_html=True)
    st.markdown(HOWTO_GUIDE)
