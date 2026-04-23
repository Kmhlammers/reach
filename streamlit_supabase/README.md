# REACH (Streamlit + Supabase)

This is a clean rewrite of the current Azure Functions + SharePoint/Graph solution into:

- **Streamlit**: UI for upload, preview, and processing.
- **Supabase (Postgres)**: storage for parsed records, issues, and totals.

The Excel parsing logic is based on the existing rules in `reach_processor.py`, but SharePoint/Graph writes are replaced by Supabase inserts.

## Local setup

1) Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r streamlit_supabase/requirements.txt
```

2) Create a Supabase project and apply the schema:

- Create a new Supabase project.
- In the Supabase SQL editor, run `streamlit_supabase/supabase/schema.sql`.

3) Provide secrets for the app (choose one):

- **Option A: Streamlit secrets file** (recommended for local):
  - Create `.streamlit/secrets.toml` at repo root or inside `streamlit_supabase/.streamlit/secrets.toml`.
  - Add:

```toml
SUPABASE_URL="https://YOURPROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY"
```

- **Option B: environment variables**:

```bash
export SUPABASE_URL="https://YOURPROJECT.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY"
```

4) Run the app:

```bash
python3 -m streamlit run streamlit_supabase/app.py
```

## What this replaces from the old system

- **GraphClient + SharePoint lists** → Supabase tables (`reach_files`, `reach_records`, `reach_issues`).
- **Azure Function HTTP endpoint** → Streamlit UI actions.

## After Streamlit Cloud (StreamlitIO) checklist

Once deployed to Streamlit Community Cloud (or Streamlit in your own infra), you still need to complete:

- **Supabase hardening**
  - Enable **Row Level Security (RLS)** and define policies (schema includes a starter section; you will likely tailor it).
  - Decide whether the Streamlit app uses **service role** (server-side only) or **user auth** (Supabase Auth).

- **Auth & access**
  - If this app must be internal-only: add Streamlit-side auth (e.g. SSO via your IdP) or place behind a reverse proxy.
  - If you want per-user data visibility: implement Supabase Auth + RLS policies.

- **Source ingestion**
  - If files currently come from SharePoint: decide ingestion approach:
    - Manual upload in Streamlit (already supported), or
    - Background sync job from SharePoint to Supabase Storage / Postgres (separate worker).

- **Background processing**
  - Streamlit is request/UI driven. For scheduled imports or batch reprocessing, add:
    - Supabase Edge Function, or
    - A GitHub Action / cron worker, or
    - A small container job (Fly.io/Render) that calls the same parsing module.

- **Email/cert workflow**
  - Your current model has fields like `Sendcertificate` and `Mailopzoeken`. Decide the new workflow:
    - Keep as flags in Postgres and build a “queue” UI, plus an email-sender job.

- **Observability**
  - Add structured logging and error reporting (Sentry, Logtail, etc.) for production.

## App pages

This Streamlit app uses multiple pages:

- `Upload & Files`: upload workbooks (auto-saves) and delete/update file metadata
- `Records`: edit/delete individual entries
- `Totals`: totals per CAS (computed from all records)

