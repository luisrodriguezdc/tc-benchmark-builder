from __future__ import annotations

import csv
import io

import pytest

from app.core.exports import EXPORT_COLUMNS, rows_to_csv
from tests.conftest import as_user, fetch_pair_id, make_user, seed_published_segments, set_pair_settings
from tests.test_allocation import _claim, _complete_batch

pytestmark = pytest.mark.db


def test_csv_writer_includes_required_columns():
    raw = rows_to_csv(
        [
            {
                "annotation_id": "a1",
                "candidate_id": "c1",
                "candidate_external_id": "ext",
                "candidate_version": 1,
                "status": "validated",
                "original_text": "old",
                "edited_text": "new",
                "annotator_email": "x@y.z",
            }
        ]
    )
    reader = csv.DictReader(io.StringIO(raw))
    assert reader.fieldnames == EXPORT_COLUMNS
    row = next(reader)
    assert row["original_text"] == "old"
    assert row["edited_text"] == "new"
    assert row["annotator_email"] == "x@y.z"
    assert row["status"] == "validated"


def test_export_query_integrity_after_annotation(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=3, iaa_pct=15)
    seed_published_segments(conn, pair, n=3)
    uid = make_user(conn, "exp@example.com")
    with as_user(conn, uid):
        batch_id = _claim(conn, pair)
        _complete_batch(conn, uid, batch_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              a.id, a.status, a.edited_text, a.error_type, a.severity,
              c.generated_text, c.external_id, c.version,
              s.external_id, p.email, b.batch_number
            FROM annotations a
            JOIN error_candidates c ON c.id = a.candidate_id
            JOIN segments s ON s.id = c.segment_id
            JOIN profiles p ON p.id = a.annotator_id
            JOIN batches b ON b.id = a.batch_id
            """
        )
        rows = cur.fetchall()
    assert rows
    for row in rows:
        assert row[1] in ("validated", "rejected", "draft")
        assert row[5]  # original generated text still present
        assert row[6]  # candidate external id
        assert row[7] >= 1
        assert row[9] == "exp@example.com"
