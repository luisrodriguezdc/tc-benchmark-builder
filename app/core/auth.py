"""Email OTP authentication and cookie-backed session restore."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from supabase import Client

from app.core.constants import COOKIE_ACCESS, COOKIE_REFRESH
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


def cookie_set_js(access_token: str, refresh_token: str) -> str:
    # Prototype: tokens live in JS-writable cookies so Streamlit can restore
    # across refresh. HttpOnly cookies cannot be set from component JS.
    def _esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    a = _esc(access_token)
    r = _esc(refresh_token)
    return f"""
<script>
(function() {{
  const maxAge = 60 * 60 * 24 * 14;
  const base = "; path=/; SameSite=Lax; max-age=" + maxAge;
  try {{
    window.parent.document.cookie = "{COOKIE_ACCESS}={a}" + base;
    window.parent.document.cookie = "{COOKIE_REFRESH}={r}" + base;
  }} catch (e) {{
    document.cookie = "{COOKIE_ACCESS}={a}" + base;
    document.cookie = "{COOKIE_REFRESH}={r}" + base;
  }}
}})();
</script>
"""


def cookie_clear_js() -> str:
    return f"""
<script>
(function() {{
  const expire = "; path=/; SameSite=Lax; max-age=0";
  try {{
    window.parent.document.cookie = "{COOKIE_ACCESS}=" + expire;
    window.parent.document.cookie = "{COOKIE_REFRESH}=" + expire;
  }} catch (e) {{
    document.cookie = "{COOKIE_ACCESS}=" + expire;
    document.cookie = "{COOKIE_REFRESH}=" + expire;
  }}
}})();
</script>
"""


def cookies_from_streamlit() -> dict[str, str]:
    try:
        import streamlit as st

        raw = st.context.cookies
        if raw is None:
            return {}
        if hasattr(raw, "to_dict"):
            return {str(k): str(v) for k, v in raw.to_dict().items()}
        return {str(k): str(v) for k, v in dict(raw).items()}
    except Exception:
        return {}


def invite_user(email: str, display_name: str, role: str = "translator") -> dict[str, Any]:
    """Create an Auth user + profile. Invitation-only; no self-signup."""
    email = email.strip().lower()
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
