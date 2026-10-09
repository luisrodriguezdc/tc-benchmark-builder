from __future__ import annotations

import threading

import pytest

from tests.conftest import as_user, fetch_pair_id, make_user, seed_published_segments, set_pair_settings

pytestmark = pytest.mark.db


def _claim(conn, pair_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT claim_batch(%s)", (pair_id,))
        row = cur.fetchone()
        return str(row[0])


def _segment_ids(conn, batch_id: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT segment_id::text FROM batch_items WHERE batch_id = %s", (batch_id,))
        return {r[0] for r in cur.fetchall()}


def _pinned_candidates(conn, batch_id: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT bic.candidate_id::text
            FROM batch_item_candidates bic
            JOIN batch_items bi ON bi.id = bic.batch_item_id
            WHERE bi.batch_id = %s
            """,
            (batch_id,),
        )
        return {r[0] for r in cur.fetchall()}


def _complete_batch(conn, uid: str, batch_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT bic.candidate_id, c.error_type, c.severity, c.generated_text
            FROM batch_item_candidates bic
            JOIN batch_items bi ON bi.id = bic.batch_item_id
            JOIN error_candidates c ON c.id = bic.candidate_id
            WHERE bi.batch_id = %s
            """,
            (batch_id,),
        )
        rows = cur.fetchall()
        for cand_id, et, sev, text in rows:
            cur.execute(
                """
                SELECT save_annotation(%s, %s, 'validated', %s, %s, %s, NULL, NULL, 0)
                """,
                (cand_id, batch_id, text, et, sev),
            )
    if not conn.autocommit:
        conn.commit()


def test_one_active_batch_rule(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=5, iaa_pct=15)
    seed_published_segments(conn, pair, n=8)
    uid = make_user(conn, "a1@example.com")
    with as_user(conn, uid):
        _claim(conn, pair)
        with pytest.raises(Exception) as exc:
            _claim(conn, pair)
    assert "already have an active batch" in str(exc.value)


def test_no_duplicate_segments_across_batches(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=4, iaa_pct=15)
    seed_published_segments(conn, pair, n=10)
    uid = make_user(conn, "a2@example.com")
    with as_user(conn, uid):
        b1 = _claim(conn, pair)
        segs1 = _segment_ids(conn, b1)
        _complete_batch(conn, uid, b1)
        b2 = _claim(conn, pair)
        segs2 = _segment_ids(conn, b2)
    assert segs1.isdisjoint(segs2)


def test_iaa_overlap_target_math_and_same_candidates(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    n = 50
    set_pair_settings(conn, pair, batch_size=100, iaa_pct=15)
    seed_published_segments(conn, pair, n=n)
    a = make_user(conn, "iaa-a@example.com")
    b = make_user(conn, "iaa-b@example.com")
    with as_user(conn, a):
        batch_a = _claim(conn, pair)
        segs_a = _segment_ids(conn, batch_a)
        pins_a = _pinned_candidates(conn, batch_a)
        _complete_batch(conn, a, batch_a)
    assert len(segs_a) == n
    with as_user(conn, b):
        batch_b = _claim(conn, pair)
        segs_b = _segment_ids(conn, batch_b)
        pins_b = _pinned_candidates(conn, batch_b)
    # 15% of 50 unique segments → 8 overlap
    assert len(segs_b) == 8
    assert segs_b.issubset(segs_a)
    overlap_pins = pins_a & pins_b
    assert overlap_pins == pins_b


def test_concurrent_claims_no_double_fresh_assignment(migrated_url):
    import psycopg2

    from tests.conftest import reset_data

    pair_conn = psycopg2.connect(migrated_url)
    pair_conn.autocommit = True
    reset_data(pair_conn)
    pair = fetch_pair_id(pair_conn)
    set_pair_settings(pair_conn, pair, batch_size=10, iaa_pct=15)
    seed_published_segments(pair_conn, pair, n=10)
    u1 = make_user(pair_conn, "c1@example.com")
    u2 = make_user(pair_conn, "c2@example.com")
    pair_conn.close()

    errors = []
    batches = {}

    def worker(uid: str, key: str) -> None:
        conn = psycopg2.connect(migrated_url)
        conn.autocommit = True
        try:
            with as_user(conn, uid):
                batches[key] = _claim(conn, pair)
        except Exception as exc:
            errors.append(exc)
        finally:
            conn.close()

    t1 = threading.Thread(target=worker, args=(u1, "a"))
    t2 = threading.Thread(target=worker, args=(u2, "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors, errors
    conn = psycopg2.connect(migrated_url)
    try:
        segs_a = _segment_ids(conn, batches["a"])
        segs_b = _segment_ids(conn, batches["b"])
        # Fresh unique segments cannot be assigned to both; overlap is allowed.
        both = segs_a & segs_b
        only_a = segs_a - segs_b
        only_b = segs_b - segs_a
        assert not (only_a and only_b and segs_a == segs_b)
        # At least one translator received the exclusive fresh set.
        assert len(segs_a | segs_b) == 10
        assert len(both) <= 2  # IAA budget ceil(10*0.15)=2
    finally:
        conn.close()
