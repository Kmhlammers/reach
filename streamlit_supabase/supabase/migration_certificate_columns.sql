-- Run once on an existing Supabase project (SQL editor).
alter table public.reach_records
  add column if not exists certificate_added boolean not null default false,
  add column if not exists certificate_file_name text null,
  add column if not exists certificate_added_at timestamptz null;
