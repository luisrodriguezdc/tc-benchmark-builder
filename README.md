# Translation Commons Benchmark Builder

Volunteer annotation tool for validating synthetic translation errors for a multilingual benchmark.

**Stack:** Streamlit + Supabase (PostgreSQL, Auth, RLS)  
**Pilot data:** 50 English → Spanish Mentoring Guidelines segments (147 generated error candidates)

This is a working multi-user prototype: invitation-only OTP login, automatic batch allocation with IAA overlap, autosaved annotations with revision history, and admin import/export.

## Translator workflow

1. Sign in with an invited email using a one-time password.
2. On the dashboard, **My Batches** is on by default. Turn it off to see other assignments (display names only — never emails).
3. Choose a language pair that still has work and click **Claim Next Batch**. The server assigns segments. You may have only one active batch at a time.
4. In the workspace, edit each generated error card, then **Validate** or **Reject**. Suggest extra errors if needed. Red underlines are a visual aid only.
5. **Back** / **Next** never discard saved work. Reopen a batch to continue from the last segment.

A segment is resolved when every generated candidate is validated or rejected. Suggestions are optional.

**Validate** means: the sentence contains exactly one intended error, it matches the selected type and severity, and there are no unrelated grammar/fluency/plausibility problems.

## Admin processes

- **Overview** — counts, translator progress, IAA coverage versus the per-pair target (default 15%).
- **Datasets** — add any number of language pairs; upload CSV (preview, then publish); archive without deleting annotation history. Published candidates already assigned to translators are never overwritten; corrections create a new version. Old batches stay pinned to the original candidate rows.
- **Volunteers** — invite, activate/deactivate, promote/demote (the last active admin cannot be removed), release or reassign abandoned batches without deleting completed work.
- **Review & export** — filter and download CSVs: all annotations, validated only, rejected/flagged, suggestions, IAA disagreements.

Only language pairs that have **published** data appear as claimable.

## Requirements

- Python **3.11+** (macOS system Python is 3.9; `brew install python@3.11`)
- A [Supabase](https://supabase.com) project (free tier is enough)
- Optional: Docker (for local pytest if `DATABASE_URL` is not set)

## Setup

### 1. Create a Supabase project

1. Open [https://supabase.com/dashboard](https://supabase.com/dashboard) and create a new project.
2. Wait until the database is ready.
3. **Authentication → Providers → Email:** enable Email. Turn **off** “Confirm email” if you want OTP-only sign-in after bootstrap (users are created already-confirmed).
4. **Authentication → Settings:** disable sign-ups / “Allow new users to sign up” so OTP cannot create users. Invitation-only is also enforced in the app (`should_create_user=False` plus a `profiles` row check).
5. Copy from **Settings → API:**
   - Project URL
   - `anon` public key
   - `service_role` secret (server-side only — never put this in client-side code)
6. Copy from **Settings → Database** the URI into `DATABASE_URL` (needed for local scripts).

### 2. Apply migrations

In the Supabase SQL editor, run the files in order:

1. [`supabase/migrations/0001_schema.sql`](supabase/migrations/0001_schema.sql)
2. [`supabase/migrations/0002_rls.sql`](supabase/migrations/0002_rls.sql)
3. [`supabase/migrations/0003_functions.sql`](supabase/migrations/0003_functions.sql)
4. [`supabase/migrations/0004_seed.sql`](supabase/migrations/0004_seed.sql)

Or, with the database URI:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
python scripts/apply_migrations.py
```

Do **not** pass `--stub-auth` against hosted Supabase (`auth` already exists). That flag is for local pytest only.

### 3. Bootstrap the first admin

```bash
python scripts/bootstrap_admin.py you@example.com "Your Name"
```

This uses the service-role key to create an Auth user and a `profiles` row with `role=admin`.

### 4. Import the Spanish pilot

```bash
python scripts/import_pilot_csv.py
```

Expected: 50 segments, 147 candidates, English → Spanish, published. Re-running is safe (upsert / skip identical rows).

CSV template for additional languages: [`data/import_template.csv`](data/import_template.csv). Any target language is allowed; add the pair in Admin → Datasets first or let the importer create it.

### 5. Run the app locally

```bash
streamlit run streamlit_app.py
```

Sign in with the admin email: request a code, then enter the OTP from the inbox (and the Supabase Auth logs if email is slow).

Invite volunteers from **Admin → Volunteers**. They sign in the same way.

### 6. Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io) → New app → this repo, main file `streamlit_app.py`.
3. In app **Settings → Secrets**, paste:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "..."
SUPABASE_SERVICE_ROLE_KEY = "..."
```

The service-role key is used only to invite users. Annotation, claiming, and admin table access run as the signed-in user through RLS.

## Tests

```bash
source .venv/bin/activate
pytest -q
```

Span tests always run. Database tests need PostgreSQL 16:

- `DATABASE_URL` if set (used in GitHub Actions), or
- Docker (`postgres:16-alpine`), or
- a local Postgres 16 install under `.pg/` (used automatically when Docker Desktop is unavailable)

Covered: allocation (one active batch, no duplicate segments, concurrent claims, 50×15% → 8 overlap, same candidate versions), annotation history and version conflicts, importer idempotency and version-on-assigned-correction, RLS / IAA blindness, export column integrity.

Covered: allocation (one active batch, no duplicate segments, concurrent claims, 50×15% → 8 overlap, same candidate versions), annotation history and version conflicts, importer idempotency and version-on-assigned-correction, RLS / IAA blindness, export column integrity.

### Manual OTP checklist

- Invited active email: code arrives, sign-in succeeds, session survives refresh.
- Unknown email: no account is created; the UI does not confirm whether the address exists.
- Deactivated profile: Auth may succeed but the app refuses access.

## Architecture

```
app/ui          Streamlit screens (dashboard, workspace, admin)
app/core        db, auth, importer, spans, allocation, exports
supabase/       SQL migrations (schema, RLS, RPCs, seed)
scripts/        bootstrap admin, import pilot, apply migrations
tests/          pytest + optional Docker Postgres
```

Authorization is enforced in PostgreSQL (RLS + `SECURITY DEFINER` functions such as `claim_batch` and `save_annotation`). Hiding admin UI is not sufficient.

## License

Prototype for Translation Commons volunteer workflow testing.
