"""Claim buttons follow language assignment. The public demo catalog stays open."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.core.allocation import batch_slot_sizes, next_open_batch_number
from app.core.auth import Profile
from app.core.constants import APP_TITLE, HOWTO_GUIDE, WELCOME_COPY
from app.core.demo import DEMO_ALEX_ID, DEMO_USER_ID, demo_profile, get_demo_client, reset_demo_store
from app.streamlit_app import production_nav_options
from app.ui.dashboard import _catalog_rows


def test_production_nav_order():
    assert production_nav_options(False) == [
        "Welcome",
        "Annotation Guide",
        "Workspace",
        "Dashboard",
    ]
    assert production_nav_options(True) == [
        "Welcome",
        "Annotation Guide",
        "Workspace",
        "Dashboard",
        "Datasets",
        "Volunteers",
        "Review & export",
    ]


def test_project_manager_reads_workspace_without_claiming(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    reset_demo_store()
    try:
        client = get_demo_client()
        store = client._store
        spanish_id = store.tables["language_pairs"][0]["id"]
        _ensure_published_segments(store, spanish_id, 12)
        profile = Profile(
            id=DEMO_USER_ID,
            email="pm@example.com",
            display_name="Project Manager",
            role="project_manager",
            is_active=True,
        )
        for row in store.tables["profiles"]:
            if row["id"] == profile.id:
                row["role"] = "project_manager"
        store.tables["translator_languages"].clear()
        store.tables["translator_languages"].append(
            {"profile_id": profile.id, "language_pair_id": spanish_id}
        )
        rows = _catalog_rows(client, profile)
        assert any(row["status"] == "Not started" for row in rows)
        assert not any(row.get("action") in {"claim", "resume", "view", "claim-dummy"} for row in rows)
        assert production_nav_options(profile.is_admin) == [
            "Welcome",
            "Annotation Guide",
            "Workspace",
            "Dashboard",
        ]
        with pytest.raises(RuntimeError, match="cannot claim"):
            client.rpc("claim_batch", {"p_language_pair_id": spanish_id}).execute()
    finally:
        reset_demo_store()


def test_project_manager_role_is_assignable():
    root = Path(__file__).resolve().parents[1]
    ui = (root / "app/ui/admin/volunteers.py").read_text(encoding="utf-8")
    sql = (root / "supabase/migrations/0009_project_manager.sql").read_text(encoding="utf-8")
    assert "project_manager" in ui
    assert "Project Manager" in ui
    assert "ADD VALUE IF NOT EXISTS 'project_manager'" in sql
    assert "is_project_manager()" in sql
    assert "Project managers cannot change this data" in sql


def test_welcome_and_annotation_guide_use_the_new_copy():
    assert "[SmartCAT Translation Score](https://www.smartcat.com/news/introducing-translation-quality-score/)" in WELCOME_COPY
    assert "[MQM](https://www.themqm.org/mqm-pillars/typology/)" in WELCOME_COPY
    assert "[ContentQuo Evaluate HT](https://www.contentquo.com/products/evaluate-ht)" in WELCOME_COPY
    assert "[TC Resource Library](https://translationcommons.org/zero-to-digital-resources/)" in WELCOME_COPY
    assert "**The data you curate will not be used to train an AI model.**" in WELCOME_COPY
    assert "*suggests an error*" in WELCOME_COPY
    assert "[Carrie Stumpf](mailto:carrie@translationcommons.org)" in WELCOME_COPY
    assert "The blue panel is the source and the reference." in WELCOME_COPY
    assert "The door is open → The door is closed" in HOWTO_GUIDE
    assert "They sell vehicles → They sell electric vehicles" in HOWTO_GUIDE
    assert "The dog with the blue collar barked → The dog barked" in HOWTO_GUIDE
    assert "**exactly one intended error.**" in HOWTO_GUIDE
    assert "Assume there is no organizational terminology database." in HOWTO_GUIDE
    assert "in your same target language" in HOWTO_GUIDE
    assert "| **Mistranslation** | Click **Save** to keep your changes. |" in HOWTO_GUIDE
    assert "**~~sharp~~**" in HOWTO_GUIDE
    assert "**~~in Room 4B~~**" in HOWTO_GUIDE
    assert "core_polarity_flip" not in HOWTO_GUIDE
    assert APP_TITLE == "Translation Commons Benchmark Builder"


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


def test_batch_slots_cover_every_published_pair(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    reset_demo_store()
    try:
        client = get_demo_client()
        store = client._store
        spanish_id = store.tables["language_pairs"][0]["id"]
        _ensure_published_segments(store, spanish_id, 12)
        french_id = _add_published_pair(store, "French", "fr-FR", batch_size=40, segments=5)
        chinese_id = _add_published_pair(store, "Chinese", "zh-CN", batch_size=2, segments=3)
        _add_published_pair(store, "German", "de-DE", batch_size=10, segments=4, dataset_status="draft")
        _add_published_pair(store, "Italian", "it-IT", batch_size=10, segments=4, active=False)
        store.tables["translator_languages"].clear()
        profile = Profile(
            id=DEMO_USER_ID,
            email="demo@example.com",
            display_name="Demo Linguist",
            role="translator",
            is_active=True,
        )
        before = len(store.tables["batches"])
        hidden = _catalog_rows(client, profile)
        assert len(store.tables["batches"]) == before
        assert not any(row.get("action") == "claim" for row in hidden)
        assert _pairs(hidden) >= {"English → Spanish", "English → French", "English → Chinese"}
        assert "English → German" not in _pairs(hidden)
        assert "English → Italian" not in _pairs(hidden)
        assert [row["size"] for row in hidden if row["pair"] == "English → French"] == ["5"]
        assert [row["size"] for row in hidden if row["pair"] == "English → Chinese"] == ["2", "1"]

        store.tables["translator_languages"].append(
            {"profile_id": profile.id, "language_pair_id": spanish_id}
        )
        shown = _catalog_rows(client, profile)
        claims = [row for row in shown if row.get("action") == "claim"]
        assert len(claims) == 1
        assert claims[0]["pair"] == "English → Spanish"
        assert claims[0]["batch"] == "1"
        assert claims[0]["_pair_id"] == spanish_id
        later = [row for row in shown if row["pair"] == "English → Spanish" and row["batch"] != "1"]
        assert later and all(row["action"] == "none" for row in later)
        assert all(row["action"] == "none" for row in shown if row["pair"] in {"English → French", "English → Chinese"})

        get_demo_client(DEMO_ALEX_ID).rpc("claim_batch", {"p_language_pair_id": spanish_id}).execute()
        shared = _catalog_rows(get_demo_client(DEMO_USER_ID), profile)
        alex_row = next(row for row in shared if row["pair"] == "English → Spanish" and row["batch"] == "1")
        assert alex_row["owner"] == "Alex"
        assert alex_row["progress"] == "—"
        assert alex_row["action"] == "none"
        assert alex_row["status"] == "WIP"
        next_claims = [row for row in shared if row.get("action") == "claim"]
        assert len(next_claims) == 1
        assert next_claims[0]["batch"] == "2"
        assert next_claims[0]["_pair_id"] == spanish_id
        assert all(row["action"] == "none" for row in shared if row.get("_pair_id") in {french_id, chinese_id})

        get_demo_client(DEMO_USER_ID).rpc("claim_batch", {"p_language_pair_id": spanish_id}).execute()
        mine = _catalog_rows(get_demo_client(DEMO_USER_ID), profile)
        assert any(row["action"] == "resume" and row["pair"] == "English → Spanish" for row in mine)
        assert not any(row.get("action") == "claim" for row in mine)
        own = next(row for row in mine if row.get("action") == "resume")
        assert own["progress"] != "—"
    finally:
        reset_demo_store()


def test_freed_batch_is_claimable_while_a_later_batch_remains(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    reset_demo_store()
    try:
        client = get_demo_client()
        store = client._store
        spanish_id = store.tables["language_pairs"][0]["id"]
        _ensure_published_segments(store, spanish_id, 12)
        store.tables["translator_languages"].clear()
        store.tables["translator_languages"].append(
            {"profile_id": DEMO_USER_ID, "language_pair_id": spanish_id}
        )
        store.tables["batches"].append(
            {
                "id": "later-batch",
                "language_pair_id": spanish_id,
                "owner_id": DEMO_ALEX_ID,
                "batch_number": 2,
                "status": "active",
            }
        )
        profile = Profile(
            id=DEMO_USER_ID,
            email="demo@example.com",
            display_name="Demo Linguist",
            role="translator",
            is_active=True,
        )
        rows = _catalog_rows(client, profile)
        claims = [row for row in rows if row.get("action") == "claim"]
        assert len(claims) == 1
        assert claims[0]["pair"] == "English → Spanish"
        assert claims[0]["batch"] == "1"
        assert claims[0]["status"] == "Not started"
        later = next(row for row in rows if row["pair"] == "English → Spanish" and row["batch"] == "2")
        assert later["action"] == "none"

        claimed = client.rpc("claim_batch", {"p_language_pair_id": spanish_id}).execute().data
        created = next(row for row in store.tables["batches"] if row["id"] == claimed)
        assert created["batch_number"] == 1
        assert any(row["id"] == "later-batch" for row in store.tables["batches"])
    finally:
        reset_demo_store()


def test_slot_size_plan():
    assert next_open_batch_number([]) == 1
    assert next_open_batch_number([2]) == 1
    assert next_open_batch_number([1, 2]) == 3
    assert batch_slot_sizes(12, 10) == [10, 2]
    assert batch_slot_sizes(20, 10) == [10, 10]
    assert batch_slot_sizes(3, 2) == [2, 1]
    assert batch_slot_sizes(0, 10) == []


def test_release_button_runs_the_delete_function():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    ui = (root / "app/ui/admin/volunteers.py").read_text(encoding="utf-8")
    sql = (root / "supabase/migrations/0007_release_unclaims.sql").read_text(encoding="utf-8")
    assert 'button("Release batch")' in ui
    assert 'client.rpc("release_batch"' in ui
    assert "DELETE FROM annotation_history" in sql
    assert "DELETE FROM annotations" in sql
    assert "DELETE FROM error_suggestions" in sql
    assert "DELETE FROM batches" in sql
    assert "SET status = 'released'" not in sql


def test_workspace_caption_stays_put():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/ui/dashboard.py").read_text(encoding="utf-8")
    assert "You are only able to claim 1 batch at a time for the languages assigned to you." in text


def _add_published_pair(
    store,
    label: str,
    target_lang: str,
    *,
    batch_size: int,
    segments: int,
    dataset_status: str = "published",
    active: bool = True,
) -> str:
    pair_id = str(uuid4())
    dataset_id = str(uuid4())
    store.tables["language_pairs"].append(
        {
            "id": pair_id,
            "source_lang": "en",
            "target_lang": target_lang,
            "source_label": "English",
            "target_label": label,
            "iaa_target_pct": 15,
            "batch_size": batch_size,
            "is_active": active,
        }
    )
    store.tables["datasets"].append(
        {
            "id": dataset_id,
            "language_pair_id": pair_id,
            "name": label,
            "version": "1",
            "status": dataset_status,
        }
    )
    for index in range(segments):
        segment_id = str(uuid4())
        store.tables["segments"].append(
            {
                "id": segment_id,
                "dataset_id": dataset_id,
                "source_text": f"{label} {index}",
                "sample_order": index + 1,
            }
        )
        store.tables["error_candidates"].append(
            {
                "id": str(uuid4()),
                "segment_id": segment_id,
                "status": "published",
            }
        )
    return pair_id


def _ensure_published_segments(store, pair_id: str, total: int) -> None:
    dataset_id = next(
        dataset["id"]
        for dataset in store.tables["datasets"]
        if dataset["language_pair_id"] == pair_id and dataset.get("status") == "published"
    )
    existing = [segment for segment in store.tables["segments"] if segment.get("dataset_id") == dataset_id]
    published = {
        candidate["segment_id"]
        for candidate in store.tables["error_candidates"]
        if candidate.get("status") == "published"
    }
    have = sum(1 for segment in existing if segment["id"] in published)
    for index in range(total - have):
        segment_id = str(uuid4())
        store.tables["segments"].append(
            {
                "id": segment_id,
                "dataset_id": dataset_id,
                "source_text": f"extra {index}",
                "sample_order": 1000 + index,
            }
        )
        store.tables["error_candidates"].append(
            {"id": str(uuid4()), "segment_id": segment_id, "status": "published"}
        )


def _pairs(rows: list[dict]) -> set[str]:
    return {row["pair"] for row in rows}


def test_release_returns_the_slot_to_not_started(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    reset_demo_store()
    try:
        client = get_demo_client()
        store = client._store
        spanish_id = store.tables["language_pairs"][0]["id"]
        _ensure_published_segments(store, spanish_id, 12)
        french_id = _add_published_pair(store, "French", "fr-FR", batch_size=40, segments=5)
        segment_count = len(store.tables["segments"])
        candidate_count = len(store.tables["error_candidates"])
        store.tables["translator_languages"].clear()
        store.tables["translator_languages"].append(
            {"profile_id": DEMO_USER_ID, "language_pair_id": spanish_id}
        )
        batch_id = client.rpc("claim_batch", {"p_language_pair_id": spanish_id}).execute().data
        item = next(row for row in store.tables["batch_items"] if row["batch_id"] == batch_id)
        candidate = next(
            row for row in store.tables["error_candidates"] if row["segment_id"] == item["segment_id"]
        )
        annotation_id = str(uuid4())
        store.tables["annotations"].append(
            {
                "id": annotation_id,
                "candidate_id": candidate["id"],
                "annotator_id": DEMO_USER_ID,
                "batch_id": batch_id,
                "status": "validated",
            }
        )
        store.tables["annotation_history"].append(
            {"id": str(uuid4()), "annotation_id": annotation_id, "rev": 1, "snapshot": {}}
        )
        store.tables["error_suggestions"].append(
            {
                "id": str(uuid4()),
                "segment_id": item["segment_id"],
                "batch_id": batch_id,
                "author_id": DEMO_USER_ID,
                "suggested_text": "keep-me-not",
            }
        )
        other_batch = str(uuid4())
        other_annotation = str(uuid4())
        store.tables["batches"].append(
            {
                "id": other_batch,
                "language_pair_id": french_id,
                "owner_id": DEMO_ALEX_ID,
                "batch_number": 1,
                "status": "active",
            }
        )
        store.tables["annotations"].append(
            {
                "id": other_annotation,
                "candidate_id": candidate["id"],
                "annotator_id": DEMO_ALEX_ID,
                "batch_id": other_batch,
                "status": "draft",
            }
        )

        client.rpc("release_batch", {"p_batch_id": batch_id}).execute()

        assert all(row["id"] != batch_id for row in store.tables["batches"])
        assert all(row.get("batch_id") != batch_id for row in store.tables["annotations"])
        assert all(row.get("annotation_id") != annotation_id for row in store.tables["annotation_history"])
        assert all(row.get("batch_id") != batch_id for row in store.tables["error_suggestions"])
        assert any(row["id"] == other_annotation for row in store.tables["annotations"])
        assert any(row["id"] == other_batch for row in store.tables["batches"])
        assert len(store.tables["segments"]) == segment_count
        assert len(store.tables["error_candidates"]) == candidate_count

        profile = Profile(
            id=DEMO_USER_ID,
            email="demo@example.com",
            display_name="Demo Linguist",
            role="translator",
            is_active=True,
        )
        rows = _catalog_rows(get_demo_client(DEMO_USER_ID), profile)
        slot = next(row for row in rows if row["pair"] == "English → Spanish" and row["batch"] == "1")
        assert slot["status"] == "Not started"
        assert slot["action"] == "claim"
        assert slot["owner"] == "—"
        assert not any(row.get("action") == "view" for row in rows if row["pair"] == "English → Spanish")
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
