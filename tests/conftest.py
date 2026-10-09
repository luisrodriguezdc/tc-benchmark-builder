from __future__ import annotations

import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "tcb-test-pg"
PORT = "55432"
PG_PREFIX = ROOT / ".pg"
PG_DATA = ROOT / ".pgdata"


def _connect(url: str):
    return psycopg2.connect(url)


def _ready(url: str, attempts: int = 40) -> None:
    last = None
    for _ in range(attempts):
        try:
            conn = _connect(url)
            conn.close()
            return
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"Postgres not ready: {last}")


def _apply_sql(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _start_local_postgres() -> str | None:
    initdb = PG_PREFIX / "bin" / "initdb"
    pg_ctl = PG_PREFIX / "bin" / "pg_ctl"
    createdb = PG_PREFIX / "bin" / "createdb"
    if not initdb.exists() or not pg_ctl.exists():
        return None
    if PG_DATA.exists():
        subprocess.run([str(pg_ctl), "-D", str(PG_DATA), "stop", "-m", "fast"], capture_output=True)
        # Reuse an existing cluster when possible.
    else:
        PG_DATA.mkdir(parents=True)
        init = subprocess.run(
            [str(initdb), "-D", str(PG_DATA), "--auth=trust", "-U", "postgres"],
            capture_output=True,
            text=True,
        )
        if init.returncode != 0:
            raise RuntimeError(f"initdb failed: {init.stderr}")
    start = subprocess.run(
        [
            str(pg_ctl),
            "-D",
            str(PG_DATA),
            "-l",
            str(ROOT / ".pgdata.log"),
            "-o",
            f"-p {PORT} -k /tmp",
            "start",
        ],
        capture_output=True,
        text=True,
    )
    if start.returncode != 0 and "another server might be running" not in (start.stderr + start.stdout):
        raise RuntimeError(f"pg_ctl start failed: {start.stderr or start.stdout}")
    url = f"postgresql://postgres@127.0.0.1:{PORT}/postgres"
    _ready(url)
    return url


@pytest.fixture(scope="session")
def database_url():
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        _ready(env_url)
        yield env_url
        return

    local_url = _start_local_postgres()
    if local_url:
        try:
            yield local_url
        finally:
            pg_ctl = PG_PREFIX / "bin" / "pg_ctl"
            subprocess.run([str(pg_ctl), "-D", str(PG_DATA), "stop", "-m", "fast"], capture_output=True)
        return

    try:
        docker = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        docker = None
    if docker is not None and docker.returncode == 0:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER,
                "-e",
                "POSTGRES_PASSWORD=postgres",
                "-p",
                f"{PORT}:5432",
                "postgres:16-alpine",
            ],
            capture_output=True,
            text=True,
        )
        if run.returncode == 0:
            url = f"postgresql://postgres:postgres@127.0.0.1:{PORT}/postgres"
            try:
                _ready(url)
                yield url
            finally:
                subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, timeout=30)
            return

    pytest.skip("No DATABASE_URL, local Postgres (.pg), or Docker available.")


@pytest.fixture(scope="session")
def migrated_url(database_url):
    conn = _connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cur.execute("CREATE SCHEMA public")
            cur.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER")
            cur.execute("GRANT ALL ON SCHEMA public TO public")
            cur.execute("DROP SCHEMA IF EXISTS auth CASCADE")
        _apply_sql(conn, ROOT / "tests" / "sql" / "auth_stub.sql")
        for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
            _apply_sql(conn, path)
        with conn.cursor() as cur:
            cur.execute("GRANT USAGE ON SCHEMA public TO authenticated, anon")
            cur.execute("GRANT authenticated TO CURRENT_USER")
    finally:
        conn.close()
    return database_url


def reset_data(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE
              annotation_history,
              annotations,
              error_suggestions,
              batch_item_candidates,
              batch_items,
              batches,
              error_candidates,
              segments,
              datasets,
              admin_audit_log,
              profiles
            RESTART IDENTITY CASCADE
            """
        )
        cur.execute("DELETE FROM auth.users")
        cur.execute(
            """
            UPDATE language_pairs
            SET batch_size = 100, iaa_target_pct = 15, is_active = true
            WHERE source_lang = 'en' AND target_lang = 'es-ES'
            """
        )
    if not conn.autocommit:
        conn.commit()


@pytest.fixture
def db(migrated_url):
    conn = _connect(migrated_url)
    conn.autocommit = False
    reset_data(conn)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def db_autocommit(migrated_url):
    conn = _connect(migrated_url)
    conn.autocommit = True
    reset_data(conn)
    yield conn
    conn.close()


def make_user(conn, email: str, role: str = "translator") -> str:
    uid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
            (uid, email),
        )
        cur.execute(
            """
            INSERT INTO profiles (id, email, display_name, role, is_active)
            VALUES (%s, %s, %s, %s, true)
            """,
            (uid, email, email.split("@")[0], role),
        )
    if not conn.autocommit:
        conn.commit()
    return uid


@contextmanager
def as_user(conn, uid: str):
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (str(uid),))
        cur.execute("SELECT set_config('request.jwt.claim.role', 'authenticated', false)")
        cur.execute("SET ROLE authenticated")
    try:
        yield conn
    finally:
        with conn.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("SELECT set_config('request.jwt.claim.sub', '', false)")


def fetch_pair_id(conn, source="en", target="es-ES") -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM language_pairs WHERE source_lang = %s AND target_lang = %s",
            (source, target),
        )
        row = cur.fetchone()
        assert row, "Seed language pair missing"
        return str(row[0])


def seed_published_segments(conn, pair_id: str, n: int = 10, n_cands: int = 3) -> list[str]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO datasets (language_pair_id, name, version, status)
            VALUES (%s, %s, %s, 'published')
            RETURNING id
            """,
            (pair_id, f"fixture-{uuid.uuid4().hex[:8]}", "1"),
        )
        dataset_id = cur.fetchone()["id"]
        segment_ids = []
        for i in range(n):
            cur.execute(
                """
                INSERT INTO segments (dataset_id, external_id, source_text, reference_text, sample_order)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    dataset_id,
                    f"seg-{i:03d}",
                    f"Source sentence {i}.",
                    f"Frase de referencia {i}.",
                    i + 1,
                ),
            )
            seg_id = cur.fetchone()["id"]
            segment_ids.append(str(seg_id))
            types = ["Mistranslation", "Addition", "Omission"]
            for j in range(n_cands):
                et = types[j % 3]
                text = f"Frase de referencia {i}."
                if et == "Mistranslation":
                    text = f"Frase de NO referencia {i}."
                elif et == "Addition":
                    text = f"Frase extra de referencia {i}."
                elif et == "Omission":
                    text = f"Frase {i}."
                cur.execute(
                    """
                    INSERT INTO error_candidates (
                      segment_id, external_id, version, status, error_type, severity, generated_text
                    ) VALUES (%s, %s, 1, 'published', %s, 'Major', %s)
                    """,
                    (seg_id, f"cand-{i:03d}-{j}", et, text),
                )
    if not conn.autocommit:
        conn.commit()
    return segment_ids


def set_pair_settings(conn, pair_id: str, *, batch_size: int, iaa_pct: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE language_pairs SET batch_size = %s, iaa_target_pct = %s WHERE id = %s",
            (batch_size, iaa_pct, pair_id),
        )
    if not conn.autocommit:
        conn.commit()
