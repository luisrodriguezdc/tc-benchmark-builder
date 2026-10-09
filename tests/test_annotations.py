from __future__ import annotations

import pytest

from tests.conftest import as_user, fetch_pair_id, make_user, seed_published_segments, set_pair_settings
from tests.test_allocation import _claim, _complete_batch

pytestmark = pytest.mark.db


def _first_candidate(conn, batch_id: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT bic.candidate_id, c.error_type, c.severity, c.generated_text
            FROM batch_item_candidates bic
            JOIN batch_items bi ON bi.id = bic.batch_item_id
            JOIN error_candidates c ON c.id = bic.candidate_id
            WHERE bi.batch_id = %s
            LIMIT 1
            """,
            (batch_id,),
        )
        return cur.fetchone()


def test_history_on_every_save(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=3, iaa_pct=15)
    seed_published_segments(conn, pair, n=3)
    uid = make_user(conn, "hist@example.com")
    with as_user(conn, uid):
        batch_id = _claim(conn, pair)
        cand_id, et, sev, text = _first_candidate(conn, batch_id)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT save_annotation(%s,%s,'draft',%s,%s,%s,NULL,NULL,0)",
                (cand_id, batch_id, text, et, sev),
            )
            cur.execute(
                "SELECT save_annotation(%s,%s,'validated',%s,%s,%s,NULL,'ok',1)",
                (cand_id, batch_id, text + "!", et, sev),
            )
            cur.execute(
                """
                SELECT count(*) FROM annotation_history h
                JOIN annotations a ON a.id = h.annotation_id
                WHERE a.candidate_id = %s AND a.annotator_id = %s
                """,
                (cand_id, uid),
            )
            assert cur.fetchone()[0] == 2
            cur.execute(
                "SELECT version, edited_text FROM annotations WHERE candidate_id = %s AND annotator_id = %s",
                (cand_id, uid),
            )
            version, edited = cur.fetchone()
            assert version == 2
            assert edited.endswith("!")


def test_version_conflict(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=3, iaa_pct=15)
    seed_published_segments(conn, pair, n=3)
    uid = make_user(conn, "conflict@example.com")
    with as_user(conn, uid):
        batch_id = _claim(conn, pair)
        cand_id, et, sev, text = _first_candidate(conn, batch_id)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT save_annotation(%s,%s,'draft',%s,%s,%s,NULL,NULL,0)",
                (cand_id, batch_id, text, et, sev),
            )
            with pytest.raises(Exception) as exc:
                cur.execute(
                    "SELECT save_annotation(%s,%s,'draft',%s,%s,%s,NULL,NULL,0)",
                    (cand_id, batch_id, "stale", et, sev),
                )
            assert "version_conflict" in str(exc.value)


def test_persistence_read_back(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=3, iaa_pct=15)
    seed_published_segments(conn, pair, n=3)
    uid = make_user(conn, "persist@example.com")
    with as_user(conn, uid):
        batch_id = _claim(conn, pair)
        cand_id, et, sev, text = _first_candidate(conn, batch_id)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT save_annotation(%s,%s,'validated',%s,%s,%s,NULL,NULL,0)",
                (cand_id, batch_id, "edited target", et, sev),
            )
    # Simulate refresh: new cursor, same DB.
    with as_user(conn, uid):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT edited_text, status FROM annotations WHERE candidate_id = %s AND annotator_id = %s",
                (cand_id, uid),
            )
            edited, status = cur.fetchone()
            assert edited == "edited target"
            assert status == "validated"
