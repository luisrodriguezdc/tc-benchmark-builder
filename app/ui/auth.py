"""OTP login screen."""

from __future__ import annotations

import streamlit as st

from app.core.auth import (
    cookie_set_js,
    fetch_profile,
    restore_session,
    send_otp,
    verify_otp,
)
from app.core.constants import APP_TITLE
from app.core.db import create_anon_client
from app.ui import styles


def render_login() -> None:
    styles.inject()
    st.markdown(f"### {APP_TITLE}")
    st.caption("Invitation-only. Use the email address Translation Commons invited.")

    if "otp_stage" not in st.session_state:
        st.session_state.otp_stage = "email"

    email = st.text_input("Email", key="login_email")
    if st.session_state.otp_stage == "email":
        if st.button("Send one-time code", type="primary"):
            if not email or "@" not in email:
                st.error("Enter a valid email address.")
                return
            try:
                send_otp(email)
            except Exception as exc:
                # Do not reveal whether the address is invited.
                st.warning(f"If this email is invited, a code was sent. ({exc.__class__.__name__})")
            else:
                st.session_state.otp_stage = "code"
                st.success("If this email is invited, a code was sent. Check your inbox.")
                st.rerun()
        return

    token = st.text_input("One-time code", key="login_otp")
    cols = st.columns(2)
    with cols[0]:
        if st.button("Verify and sign in", type="primary"):
            try:
                access, refresh = verify_otp(email, token)
                client = restore_session(access, refresh)
                profile = fetch_profile(client)
            except Exception as exc:
                st.error(f"Could not verify that code. {exc}")
                return
            if profile is None or not profile.is_active:
                st.error("This account is not invited or has been deactivated.")
                return
            st.session_state.access_token = access
            st.session_state.refresh_token = refresh
            st.session_state.client = client
            st.session_state.profile = profile
            st.session_state.page = "dashboard"
            st.components.v1.html(cookie_set_js(access, refresh), height=0)
            st.rerun()
    with cols[1]:
        if st.button("Use a different email"):
            st.session_state.otp_stage = "email"
            st.rerun()


def healthcheck() -> str | None:
    from app.core.demo import demo_enabled

    if demo_enabled():
        return None
    try:
        create_anon_client()
    except Exception as exc:
        return str(exc)
    return None
