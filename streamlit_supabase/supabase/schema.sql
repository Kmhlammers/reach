-- Supabase schema for REACH processing
-- Safe to run on a new project. If you re-run, you may want to drop first.

create extension if not exists pgcrypto;

-- ---------- Core entities ----------

create table if not exists public.reach_files (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),

  -- source metadata (kept generic so you can ingest from upload/sharepoint/etc.)
  source_type text not null,
  source_ref text null,

  file_name text not null,
  file_sha256 text null,
  notes text null
);

create table if not exists public.reach_records (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),

  file_id uuid not null references public.reach_files(id) on delete cascade,

  row_key text not null,
  sheet text null,

  supplier_name text null,
  supplier_name_original text null,

  cas_number text not null,
  substance text null,
  or_registered text null,

  total_kg double precision not null default 0,
  total_tonnes double precision not null default 0,

  import_status text not null default 'processed',
  import_message text null,

  processed_at timestamptz null,

  certificate_added boolean not null default false,
  certificate_file_name text null,
  certificate_added_at timestamptz null
);

create unique index if not exists reach_records_file_rowkey_uq
  on public.reach_records(file_id, row_key);

create table if not exists public.reach_issues (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),

  file_id uuid not null references public.reach_files(id) on delete cascade,
  sheet text null,

  issue_type text not null,
  message text not null,
  row_key text null
);

-- ---------- Totals (computed) ----------
-- Using a view keeps totals always consistent and avoids sync logic.

create or replace view public.reach_totals as
select
  cas_number,
  max(substance) as substance,
  sum(total_kg) as total_kg,
  sum(total_tonnes) as total_tonnes,
  count(*) as record_count
from public.reach_records
group by cas_number;

create or replace view public.reach_totals_yearly as
select
  extract(year from coalesce(created_at, processed_at) at time zone 'UTC')::int as year,
  cas_number,
  max(substance) as substance,
  sum(total_kg) as total_kg,
  sum(total_tonnes) as total_tonnes,
  count(*) as record_count
from public.reach_records
group by year, cas_number;

create or replace view public.reach_years as
select distinct
  extract(year from coalesce(created_at, processed_at) at time zone 'UTC')::int as year
from public.reach_records
order by year desc;

-- ---------- RLS starter (adjust to your needs) ----------
-- If you plan to use only the service-role key from Streamlit (server-side),
-- you can keep RLS disabled. If you want user-level access, enable RLS and
-- implement policies based on auth.uid() and an ownership model.

-- alter table public.reach_files enable row level security;
-- alter table public.reach_records enable row level security;
-- alter table public.reach_issues enable row level security;
--
-- Example: allow authenticated users to read everything (NOT recommended for multi-tenant)
-- create policy "read all reach_files" on public.reach_files
--   for select to authenticated using (true);

