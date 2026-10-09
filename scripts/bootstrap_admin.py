#!/usr/bin/env python3
"""Create the first admin user (Auth + profiles.role = admin)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from app.core.auth import invite_user
from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.supabase_service_role_key:
        sys.exit("SUPABASE_SERVICE_ROLE_KEY is required.")
    email = os.environ.get("ADMIN_EMAIL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    name = os.environ.get("ADMIN_DISPLAY_NAME") or (sys.argv[2] if len(sys.argv) > 2 else "Admin")
    if not email:
        sys.exit("Usage: python scripts/bootstrap_admin.py EMAIL [DISPLAY_NAME]")
    row = invite_user(email, name, role="admin")
    print(f"Admin ready: {row['email']} ({row['id']})")
    print("Sign in through the app with an email OTP. Confirm Auth settings:")
    print("  - Disable automatic sign-ups / 'confirm email' as needed")
    print("  - Enable Email OTP / magic link")


if __name__ == "__main__":
    main()
