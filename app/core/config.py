"""Load settings from Streamlit secrets or environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _secret(*names: str, default: str = "") -> str:
    try:
        import streamlit as st

        for name in names:
            if name in st.secrets:
                return str(st.secrets[name])
    except Exception:
        pass
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str
    database_url: str

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


def get_settings() -> Settings:
    return Settings(
        supabase_url=_secret("SUPABASE_URL"),
        supabase_publishable_key=_secret(
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_ANON_KEY",
        ),
        supabase_secret_key=_secret(
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
        database_url=_secret("DATABASE_URL"),
    )
