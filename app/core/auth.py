"""Email OTP authentication and cookie-backed session restore."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from supabase import Client

from app.core.constants import COOKIE_ACCESS, COOKIE_REFRESH

# Sliding lifetime of the browser session. Each signed-in page view refreshes it.
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 14
from app.core.db import create_anon_client, create_service_client


@dataclass
class Profile:
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" and self.is_active

    @property
    def is_project_manager(self) -> bool:
        return self.role == "project_manager" and self.is_active


def send_otp(email: str) -> None:
    client = create_anon_client()
    client.auth.sign_in_with_otp(
        {
            "email": email.strip(),
            "options": {"should_create_user": False},
        }
    )


def verify_otp(email: str, token: str) -> tuple[str, str]:
    client = create_anon_client()
    result = client.auth.verify_otp(
        {
            "email": email.strip(),
            "token": token.strip(),
            "type": "email",
        }
    )
    session = result.session
    if session is None or not session.access_token or not session.refresh_token:
        raise RuntimeError("OTP verification did not return a session.")
    return session.access_token, session.refresh_token


def restore_session(access_token: str, refresh_token: str) -> Client:
    from app.core.db import client_for_user

    return client_for_user(access_token, refresh_token)


def fetch_profile(client: Client) -> Profile | None:
    user = client.auth.get_user()
    if not user or not user.user:
        return None
    uid = user.user.id
    res = client.table("profiles").select("*").eq("id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        return None
    row = rows[0]
    return Profile(
        id=row["id"],
        email=row["email"],
        display_name=row.get("display_name") or row["email"].split("@")[0],
        role=row["role"],
        is_active=bool(row["is_active"]),
    )


def persisted_tokens(client: Client, access_token: str, refresh_token: str) -> tuple[str, str]:
    """Return the session the client is actually using.

    ``set_session`` refreshes an expired access token. The cookie must store
    that new pair, not the expired access token that was just exchanged.
    """
    try:
        session = client.auth.get_session()
    except Exception:
        session = None
    access = getattr(session, "access_token", None) if session else None
    refresh = getattr(session, "refresh_token", None) if session else None
    if access and refresh:
        return str(access), str(refresh)
    return access_token, refresh_token


def cookie_set_js(access_token: str, refresh_token: str) -> str:
    """Write the user session onto the page that Streamlit is serving.

    A component iframe cannot set a cookie the next full page load will send.
    Values are encoded because a JWT contains ``=``.
    """
    payload = json.dumps(
        {COOKIE_ACCESS: access_token, COOKIE_REFRESH: refresh_token}
    ).replace("<", "\\u003c")
    return f"""
<div class="tcb-auth-cookie" hidden></div>
<script>
(function() {{
  const maxAge = {SESSION_COOKIE_MAX_AGE};
  const items = {payload};
  const base = "; path=/; SameSite=Lax; max-age=" + maxAge;
  Object.keys(items).forEach(function(name) {{
    document.cookie = name + "=" + encodeURIComponent(items[name]) + base;
  }});
}})();
</script>
"""


def cookie_clear_js() -> str:
    return f"""
<div class="tcb-auth-cookie" hidden></div>
<script>
(function() {{
  const expire = "; path=/; SameSite=Lax; max-age=0";
  document.cookie = "{COOKIE_ACCESS}=" + expire;
  document.cookie = "{COOKIE_REFRESH}=" + expire;
}})();
</script>
"""


def decode_cookie_jar(raw: dict) -> dict[str, str]:
    return {str(key): unquote(str(value)) for key, value in raw.items()}


def cookies_from_streamlit() -> dict[str, str]:
    try:
        import streamlit as st

        raw = st.context.cookies
        if raw is None:
            return {}
        if hasattr(raw, "to_dict"):
            items = raw.to_dict().items()
        else:
            items = dict(raw).items()
        return decode_cookie_jar(dict(items))
    except Exception:
        return {}


def invite_user(email: str, display_name: str, role: str = "translator") -> dict[str, Any]:
    """Create an Auth user + profile. Invitation-only; no self-signup."""
    from app.core.demo import demo_enabled, get_demo_store

    email = email.strip().lower()
    if demo_enabled():
        return get_demo_store().invite(email, display_name, role)
    admin = create_service_client()
    created = admin.auth.admin.create_user(
        {
            "email": email,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name},
        }
    )
    user = created.user
    if user is None:
        raise RuntimeError("Failed to create auth user.")
    row = {
        "id": user.id,
        "email": email,
        "display_name": display_name or email.split("@")[0],
        "role": role,
        "is_active": True,
    }
    admin.table("profiles").upsert(row, on_conflict="id").execute()
    return row
