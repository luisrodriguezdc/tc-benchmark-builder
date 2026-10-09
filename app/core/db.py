"""Supabase client factory. Secret key is never exposed to the browser."""

from __future__ import annotations

from supabase import Client, create_client

from app.core.config import Settings, get_settings


def create_anon_client(settings: Settings | None = None) -> Client:
    settings = settings or get_settings()
    if not settings.configured:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY. "
            "Copy .env.example to .env or set Streamlit secrets."
        )
    return create_client(settings.supabase_url, settings.supabase_publishable_key)


def create_service_client(settings: Settings | None = None) -> Client:
    settings = settings or get_settings()
    if not settings.supabase_secret_key:
        raise RuntimeError("Missing SUPABASE_SECRET_KEY (server-side secret only).")
    return create_client(settings.supabase_url, settings.supabase_secret_key)


def client_for_user(access_token: str, refresh_token: str, settings: Settings | None = None) -> Client:
    client = create_anon_client(settings)
    client.auth.set_session(access_token, refresh_token)
    return client
