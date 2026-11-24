"""The signed-in session is stored on the page, not in an iframe."""

from __future__ import annotations

from pathlib import Path

from app.core.auth import (
    SESSION_COOKIE_MAX_AGE,
    cookie_clear_js,
    cookie_set_js,
    decode_cookie_jar,
    persisted_tokens,
)
from app.core.constants import APP_TITLE, COOKIE_ACCESS, COOKIE_REFRESH


def test_login_page_shows_the_app_title():
    source = Path(__file__).resolve().parents[1].joinpath("app/ui/auth.py").read_text(encoding="utf-8")
    assert f'st.markdown(f"### {{APP_TITLE}}")' in source
    assert APP_TITLE == "Translation Commons Benchmark Builder"


def test_session_cookie_is_written_on_the_page():
    script = cookie_set_js("access.part.with=padding", "refresh-token")
    assert "document.cookie" in script
    assert "encodeURIComponent" in script
    assert "window.parent" not in script
    assert str(SESSION_COOKIE_MAX_AGE) in script
    assert SESSION_COOKIE_MAX_AGE == 60 * 60 * 24 * 14
    assert "service_role" not in script
    assert "SUPABASE_SECRET" not in script
    assert COOKIE_ACCESS in script
    assert COOKIE_REFRESH in script
    cleared = cookie_clear_js()
    assert "document.cookie" in cleared
    assert "max-age=0" in cleared
    assert "window.parent" not in cleared


def test_cookie_values_are_decoded():
    raw = {COOKIE_ACCESS: "abc%3Ddef", COOKIE_REFRESH: "plain"}
    assert decode_cookie_jar(raw) == {COOKIE_ACCESS: "abc=def", COOKIE_REFRESH: "plain"}


def test_refreshed_session_replaces_the_expired_access_token():
    class _Session:
        access_token = "new-access"
        refresh_token = "new-refresh"

    class _Auth:
        def get_session(self):
            return _Session()

    class _Client:
        auth = _Auth()

    assert persisted_tokens(_Client(), "expired-access", "old-refresh") == (
        "new-access",
        "new-refresh",
    )

    class _Broken:
        def get_session(self):
            raise RuntimeError("no session")

    class _BrokenClient:
        auth = _Broken()

    assert persisted_tokens(_BrokenClient(), "keep-access", "keep-refresh") == (
        "keep-access",
        "keep-refresh",
    )
