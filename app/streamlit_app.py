"""Application entry: auth gate and role-based routing."""

from __future__ import annotations

import streamlit as st

from app.core.auth import cookie_set_js, cookies_from_streamlit, fetch_profile, persisted_tokens, restore_session
from app.core.constants import APP_TITLE, COOKIE_ACCESS, COOKIE_REFRESH
from app.core.demo import demo_enabled, demo_profile, get_demo_client, reset_demo_store
from app.ui.admin.datasets import render_datasets
from app.ui.admin.exports import render_exports
from app.ui.admin.overview import render_overview
from app.ui.admin.volunteers import render_volunteers
from app.ui.auth import healthcheck, render_login
from app.ui.components import render_account_menu, render_sidebar_nav
from app.ui.dashboard import render_dashboard
from app.ui.welcome import render_howto, render_welcome
from app.ui.workspace import render_workspace
from app.ui import styles

VOLUNTEER_NAV = ("Welcome", "Annotation Guide", "Workspace", "Dashboard")
ADMIN_NAV = ("Datasets", "Volunteers", "Review & export")


def production_nav_options(is_admin: bool) -> list[str]:
    options = list(VOLUNTEER_NAV)
    if is_admin:
        options.extend(ADMIN_NAV)
    return options


def _restore_from_cookies() -> None:
    if st.session_state.get("clear_auth_cookies"):
        return
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
        st.session_state.clear_auth_cookies = True
        return
    if profile is None or not profile.is_active:
        st.session_state.clear_auth_cookies = True
        return
    access, refresh = persisted_tokens(client, access, refresh)
    st.session_state.client = client
    st.session_state.profile = profile
    st.session_state.access_token = access
    st.session_state.refresh_token = refresh
    st.session_state.page = st.session_state.get("page") or "dashboard"


def _reset_demo() -> None:
    reset_demo_store()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.client = get_demo_client()
    st.session_state.profile = demo_profile()
    st.session_state.page = "dashboard"


def run() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    if demo_enabled():
        if st.session_state.get("client") is None:
            st.session_state.client = get_demo_client()
            st.session_state.profile = demo_profile()
            st.session_state.page = "dashboard"
        _run_app()
        return

    err = healthcheck()
    if err:
        st.error(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY "
            f"in .env or Streamlit secrets.\n\n{err}"
        )
        st.stop()

    _restore_from_cookies()

    _run_app()


def _run_app() -> None:
    profile = st.session_state.get("profile")
    client = st.session_state.get("client")
    if profile is None or client is None:
        render_login()
        return
    if demo_enabled():
        _run_demo(client, profile)
        return
    _run_production(client, profile)


def _run_demo(client, profile) -> None:
    styles.inject()
    _route(client, profile)
    if st.sidebar.button("Reset Demo", key="reset_demo"):
        _reset_demo()
        st.rerun()
    render_account_menu(profile)


def _run_production(client, profile) -> None:
    styles.inject()
    access = st.session_state.get("access_token") or ""
    refresh = st.session_state.get("refresh_token") or ""
    if access and refresh:
        access, refresh = persisted_tokens(client, access, refresh)
        st.session_state.access_token = access
        st.session_state.refresh_token = refresh
        st.html(cookie_set_js(access, refresh), unsafe_allow_javascript=True)
    _route(client, profile)
    render_account_menu(profile)


def _route(client, profile) -> None:
    options = production_nav_options(profile.is_admin)
    choice = render_sidebar_nav(options)

    # Leaving the batch list closes an open annotation screen.
    if choice != "Workspace":
        st.session_state.page = "dashboard"

    if choice == "Welcome":
        render_welcome(profile)
    elif choice == "Annotation Guide":
        render_howto()
    elif choice == "Dashboard":
        render_overview(client)
    elif choice == "Datasets":
        render_datasets(client)
    elif choice == "Volunteers":
        render_volunteers(client)
    elif choice == "Review & export":
        render_exports(client)
    elif st.session_state.get("page") == "workspace" and not profile.is_project_manager:
        render_workspace(client, profile)
    else:
        st.session_state.page = "dashboard"
        render_dashboard(client, profile)
