from __future__ import annotations

import pytest

from tests.conftest import as_user, fetch_pair_id, make_user, seed_published_segments, set_pair_settings
from tests.test_allocation import _claim, _complete_batch

pytestmark = pytest.mark.db


def test_translator_cannot_read_other_annotations(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    set_pair_settings(conn, pair, batch_size=5, iaa_pct=40)
    seed_published_segments(conn, pair, n=5)
    a = make_user(conn, "rls-a@example.com")
    b = make_user(conn, "rls-b@example.com")
    admin = make_user(conn, "rls-admin@example.com", role="admin")

    with as_user(conn, a):
        batch_a = _claim(conn, pair)
        _complete_batch(conn, a, batch_a)

    with as_user(conn, b):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM annotations")
            # IAA blindness: B must not see A's judgments.
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT email FROM profiles WHERE id = %s", (a,))
            # Email of another volunteer is not readable.
            assert cur.fetchone() is None
            cur.execute("SELECT display_name FROM profiles_public WHERE id = %s", (a,))
            name = cur.fetchone()
            assert name is not None

    with as_user(conn, admin):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM annotations")
            assert cur.fetchone()[0] > 0
            cur.execute("SELECT email FROM profiles WHERE id = %s", (a,))
            assert cur.fetchone() is not None


def test_translator_cannot_select_unassigned_segments(db_autocommit):
    conn = db_autocommit
    pair = fetch_pair_id(conn)
    seed_published_segments(conn, pair, n=4)
    uid = make_user(conn, "rls-c@example.com")
    with as_user(conn, uid):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM segments")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM error_candidates")
            assert cur.fetchone()[0] == 0
