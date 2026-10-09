"""Load settings from Streamlit secrets or environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)


def get_settings() -> Settings:
    return Settings(
        supabase_url=_secret("SUPABASE_URL"),
        supabase_anon_key=_secret("SUPABASE_ANON_KEY"),
        supabase_service_role_key=_secret("SUPABASE_SERVICE_ROLE_KEY"),
        database_url=_secret("DATABASE_URL"),
    )
