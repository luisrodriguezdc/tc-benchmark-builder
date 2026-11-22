"""Claim buttons follow language assignment. The public demo catalog stays open."""

from __future__ import annotations

from app.core.auth import Profile
from app.core.demo import DEMO_USER_ID, demo_profile, get_demo_client, reset_demo_store
from app.streamlit_app import production_nav_options
from app.ui.dashboard import _catalog_rows


def test_production_nav_order():
    assert production_nav_options(False) == ["Welcome", "How To Guide", "Dashboard"]
    assert production_nav_options(True) == [
        "Welcome",
        "How To Guide",
        "Dashboard",
        "Overview",
        "Datasets",
        "Volunteers",
        "Review & export",
    ]


def test_claim_button_follows_assignment_outside_demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    reset_demo_store()
    try:
        client = get_demo_client()
        profile = Profile(
            id=DEMO_USER_ID,
            email="demo@example.com",
            display_name="Demo Linguist",
            role="translator",
            is_active=True,
        )
        client._store.tables["translator_languages"].clear()
        hidden = _catalog_rows(client, profile)
        assert not any(row.get("action") == "claim" for row in hidden)
        assert any(row["status"] == "Not started" and row["action"] == "none" for row in hidden)

        pair_id = client._store.tables["language_pairs"][0]["id"]
        client._store.tables["translator_languages"].append(
            {"profile_id": profile.id, "language_pair_id": pair_id}
        )
        shown = _catalog_rows(client, profile)
        assert any(row.get("action") == "claim" and row.get("_pair_id") == pair_id for row in shown)
    finally:
        reset_demo_store()


def test_demo_catalog_still_offers_sample_claims(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    reset_demo_store()
    try:
        client = get_demo_client()
        client._store.tables["translator_languages"].clear()
        rows = _catalog_rows(client, demo_profile())
        assert any(row.get("action") == "claim" for row in rows)
        assert any(row.get("action") == "claim-dummy" and row["pair"] == "English → French" for row in rows)
    finally:
        reset_demo_store()


def test_demo_language_assignment_roundtrip():
    reset_demo_store()
    try:
        client = get_demo_client()
        pair_id = client._store.tables["language_pairs"][0]["id"]
        client.table("translator_languages").delete().eq("profile_id", DEMO_USER_ID).execute()
        empty = (
            client.table("translator_languages")
            .select("language_pair_id")
            .eq("profile_id", DEMO_USER_ID)
            .execute()
            .data
        )
        assert empty == []
        client.table("translator_languages").insert(
            [{"profile_id": DEMO_USER_ID, "language_pair_id": pair_id}]
        ).execute()
        rows = (
            client.table("translator_languages")
            .select("language_pair_id")
            .eq("profile_id", DEMO_USER_ID)
            .execute()
            .data
        )
        assert rows == [{"language_pair_id": pair_id}]
    finally:
        reset_demo_store()
