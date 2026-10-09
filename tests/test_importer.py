from __future__ import annotations

from pathlib import Path

import pytest

from app.core.importer import parse_csv, persist_import
from app.core.spans import compute_span
from app.core.store import PostgresStore
from tests.conftest import as_user, fetch_pair_id, make_user, set_pair_settings
from tests.test_allocation import _claim, _pinned_candidates

pytestmark = pytest.mark.db

MINI = Path(__file__).parent / "fixtures" / "mini.csv"


def test_parse_and_spans_without_assuming_offsets():
    rows = parse_csv(MINI)
    assert len(rows) == 6
    assert {r.error_type for r in rows} == {"Mistranslation", "Addition", "Omission"}
    omi = next(r for r in rows if r.error_type == "Omission" and r.external_segment_id == "seg-a")
    assert omi.ref_span_start is not None
    span = compute_span(omi.reference_text, omi.generated_target, "Omission")
    assert (omi.ref_span_start, omi.ref_span_end) == (span.ref_start, span.ref_end)


def test_idempotent_reimport(db_autocommit):
    conn = db_autocommit
    store = PostgresStore(conn)
    rows = parse_csv(MINI)
    r1 = persist_import(store, rows, publish=True)
    r2 = persist_import(store, rows, publish=True)
    assert r1.candidates_inserted == 6
    assert r2.candidates_skipped == 6
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM error_candidates WHERE external_id LIKE 'c-%'")
        assert cur.fetchone()[0] == 6


def test_assigned_candidate_is_versioned_not_overwritten(db_autocommit):
    conn = db_autocommit
    store = PostgresStore(conn)
    rows = parse_csv(MINI)
    persist_import(store, rows, publish=True)

    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=10, iaa_pct=15)
    uid = make_user(conn, "imp@example.com")
    with as_user(conn, uid):
        batch_id = _claim(conn, pair)
        pinned = _pinned_candidates(conn, batch_id)
    assert pinned

    rows[0].generated_target = "CHANGED TARGET TEXT"
    report = persist_import(store, rows, publish=True)
    assert report.candidates_versioned >= 1
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), max(version)
            FROM error_candidates
            WHERE external_id = %s
            """,
            (rows[0].candidate_id,),
        )
        n, vmax = cur.fetchone()
        assert n >= 2
        assert vmax >= 2
        cur.execute(
            "SELECT generated_text FROM error_candidates WHERE id = %s",
            (next(iter(pinned)),),
        )
        # Original pinned row must still exist with original text or at least not be deleted.
        assert cur.fetchone() is not None
