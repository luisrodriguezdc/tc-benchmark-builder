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
5. Copy keys from **Project Settings → API Keys**. Use the **Publishable and secret API keys** tab (not the legacy `anon` / `service_role` JWTs, which Supabase is deprecating):
   - Project URL (from **Settings → Data API** or the project homepage)
   - **Publishable** key (`sb_publishable_...`) → `SUPABASE_PUBLISHABLE_KEY`
   - **Secret** key (`sb_secret_...`) → `SUPABASE_SECRET_KEY` (server-side only — never commit it)
6. Copy from **Settings → Database** the URI into `DATABASE_URL` (needed for local scripts).
7. Set up **Resend** for Auth emails (recommended). The built-in Supabase mailer is limited to **2 emails per hour**, which is too low for volunteer testing. See [Custom SMTP with Resend](#custom-smtp-with-resend) below.

### 2. Apply migrations

In the Supabase SQL editor, run the files in order:

1. [`supabase/migrations/0001_schema.sql`](supabase/migrations/0001_schema.sql)
2. [`supabase/migrations/0002_rls.sql`](supabase/migrations/0002_rls.sql)
3. [`supabase/migrations/0003_functions.sql`](supabase/migrations/0003_functions.sql)
4. [`supabase/migrations/0004_seed.sql`](supabase/migrations/0004_seed.sql)
5. [`supabase/migrations/0005_source_error.sql`](supabase/migrations/0005_source_error.sql)

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

This uses the secret API key to create an Auth user and a `profiles` row with `role=admin`.

### 4. Import the Spanish pilot

```bash
python scripts/import_pilot_csv.py
```

Expected: 50 segments, 147 candidates, English → Spanish, published. Re-running is safe (upsert / skip identical rows).

CSV template for additional languages: [`data/import_template.csv`](data/import_template.csv). Any target language is allowed; add the pair in Admin → Datasets first or let the importer create it.

### 5. Run the app locally

Without Supabase, you can open a local demo (12 real pilot segments, in memory):

```bash
DEMO_MODE=1 streamlit run streamlit_app.py
```

You are signed in as **Demo Linguist** (admin). Claim a batch on the dashboard to open the annotation workspace. Nothing is persisted.

With Supabase configured:

```bash
streamlit run streamlit_app.py
```

Sign in with the admin email: request a code, then enter the OTP from the inbox (and the Supabase Auth logs if email is slow).

Invite volunteers from **Admin → Volunteers**. They sign in the same way.

### 6. Deploy on Streamlit Community Cloud

You can ship the in-memory demo (what you tested locally) without setting up Supabase. Annotations and claims reset whenever the Cloud app sleeps or restarts, and concurrent visitors can share or clobber the same in-memory store.

1. Push this repository to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io) → **New app** → this repo, branch `main`, main file `streamlit_app.py`. Use Python 3.11 or 3.12.
3. In **Settings → Secrets**, paste:

```toml
DEMO_MODE = "1"
```

If secrets are empty and no Supabase keys are set, the app also falls back to demo mode.

When you later add a real backend, remove `DEMO_MODE` and set:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."
SUPABASE_SECRET_KEY = "sb_secret_..."
```

The secret key is used only to invite users. Annotation, claiming, and admin table access run as the signed-in user through RLS. Do not disable legacy API keys in Supabase until this app is running on the publishable/secret pair. Also run `0005_source_error.sql` with the other migrations.

## Custom SMTP with Resend

Supabase’s built-in mailer allows **2 OTP emails per hour per project**. For more than a couple of test logins, send Auth mail through [Resend](https://resend.com) (free tier is enough for this prototype).

### A. Create a Resend account and API key

1. Sign up at [https://resend.com](https://resend.com).
2. **Domains → Add Domain** and verify a domain you control (DNS records Resend shows for MX/TXT/CNAME). OTP From-addresses must use this domain. `onboarding@resend.dev` only works for sending to *your own* Resend account email, not to volunteers.
3. **API Keys → Create** with permission **Sending access**. Copy the key (`re_...`). Treat it like a password.

### B. Point Supabase Auth at Resend SMTP

In the Supabase dashboard: **Authentication → Emails → SMTP Settings** (wording may be **Authentication → Notifications → Email → SMTP Settings**). Enable custom SMTP and use:

| Field | Value |
|---|---|
| Sender email | `noreply@YOUR_VERIFIED_DOMAIN` |
| Sender name | Translation Commons Benchmark Builder |
| Host | `smtp.resend.com` |
| Port | `465` (implicit TLS). If that times out, try `587`. |
| Username | `resend` (literal string, not your email) |
| Password | your Resend API key (`re_...`) |

Save. Optionally send a test from that screen.

### C. Raise the Auth email rate limit

After custom SMTP is on, go to **Authentication → Rate Limits** and raise **Emails sent** above the default (~30/hour) if several volunteers will log in in the same hour. The 60-second per-user OTP cooldown still applies.

### D. Check delivery

- OTP codes appear in the volunteer’s inbox (and spam, the first time).
- Failed sends show in **Supabase → Authentication → Logs** and **Resend → Emails**.
- Bootstrap/invite (`scripts/bootstrap_admin.py` and Admin → Volunteers) does **not** send mail; only **Send one-time code** on the login screen does.

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
