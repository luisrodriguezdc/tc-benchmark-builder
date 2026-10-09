"""Application entry: auth gate and role-based routing."""

from __future__ import annotations

import streamlit as st

from app.core.auth import cookies_from_streamlit, fetch_profile, restore_session
from app.core.constants import APP_TITLE, COOKIE_ACCESS, COOKIE_REFRESH
from app.ui.admin.datasets import render_datasets
from app.ui.admin.exports import render_exports
from app.ui.admin.overview import render_overview
from app.ui.admin.volunteers import render_volunteers
from app.ui.auth import healthcheck, render_login
from app.ui.dashboard import render_dashboard
from app.ui.workspace import render_workspace


def _restore_from_cookies() -> None:
    if st.session_state.get("client") is not None:
        return
    cookies = cookies_from_streamlit()
    access = cookies.get(COOKIE_ACCESS)
    refresh = cookies.get(COOKIE_REFRESH)
    if not access or not refresh:
        return
    try:
        client = restore_session(access, refresh)
        profile = fetch_profile(client)
    except Exception:
        return
    if profile is None or not profile.is_active:
        return
    st.session_state.client = client
    st.session_state.profile = profile
    st.session_state.access_token = access
    st.session_state.refresh_token = refresh
    st.session_state.page = st.session_state.get("page") or "dashboard"


def run() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="auto")
    err = healthcheck()
    if err:
        st.error(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY "
            f"in .env or Streamlit secrets.\n\n{err}"
        )
        st.stop()

    _restore_from_cookies()

    profile = st.session_state.get("profile")
    client = st.session_state.get("client")
    if profile is None or client is None:
        render_login()
        return

    page = st.session_state.get("page") or "dashboard"

    if profile.is_admin:
        mode = st.sidebar.radio("Mode", ["Translator", "Admin"], index=0 if page != "admin" else 1)
    else:
        mode = "Translator"

    if mode == "Admin":
        section = st.sidebar.radio("Admin", ["Overview", "Datasets", "Volunteers", "Review & export"])
        if section == "Overview":
            render_overview(client)
        elif section == "Datasets":
            render_datasets(client)
        elif section == "Volunteers":
            render_volunteers(client)
        else:
            render_exports(client)
        return

    if page == "workspace":
        render_workspace(client, profile)
    else:
        render_dashboard(client, profile)
