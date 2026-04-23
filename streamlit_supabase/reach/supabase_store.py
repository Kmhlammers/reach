import os
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from supabase import Client, create_client


def _get_secret(name: str) -> Optional[str]:
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name)


def get_supabase_client() -> Client:
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_SERVICE_ROLE_KEY") or _get_secret("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY).")
    return create_client(url, key)


def create_file_row(
    sb: Client,
    *,
    source_type: str,
    source_ref: Optional[str],
    file_name: str,
    file_sha256: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    payload: Dict[str, Any] = {
        "source_type": source_type,
        "source_ref": source_ref,
        "file_name": file_name,
        "file_sha256": file_sha256,
        "notes": notes,
    }
    resp = sb.table("reach_files").insert(payload).execute()
    return resp.data[0]["id"]


def upsert_records(sb: Client, *, file_id: str, records: List[Dict[str, Any]]) -> Tuple[int, int]:
    if not records:
        return 0, 0

    rows = [{**r, "file_id": file_id} for r in records]
    resp = sb.table("reach_records").upsert(rows, on_conflict="file_id,row_key").execute()

    # Supabase doesn't reliably distinguish inserts vs updates in response.
    # We return "written" and "attempted" counts for now.
    written = len(resp.data or [])
    attempted = len(rows)
    return written, attempted


def insert_issues(sb: Client, *, file_id: str, issues: List[Dict[str, Any]]) -> int:
    if not issues:
        return 0
    rows = [{**i, "file_id": file_id} for i in issues]
    resp = sb.table("reach_issues").insert(rows).execute()
    return len(resp.data or [])


def list_files(sb: Client, *, limit: int = 200) -> List[Dict[str, Any]]:
    resp = sb.table("reach_files").select("*").order("created_at", desc=True).limit(limit).execute()
    return resp.data or []


def get_file(sb: Client, *, file_id: str) -> Optional[Dict[str, Any]]:
    resp = sb.table("reach_files").select("*").eq("id", file_id).limit(1).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def update_file(sb: Client, *, file_id: str, patch: Dict[str, Any]) -> None:
    sb.table("reach_files").update(patch).eq("id", file_id).execute()


def delete_file(sb: Client, *, file_id: str) -> None:
    # cascades to reach_records and reach_issues via FK on delete cascade
    sb.table("reach_files").delete().eq("id", file_id).execute()


def list_records(
    sb: Client,
    *,
    file_id: Optional[str] = None,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    q = sb.table("reach_records").select("*").order("created_at", desc=True).limit(limit)
    if file_id:
        q = q.eq("file_id", file_id)
    resp = q.execute()
    return resp.data or []


def update_record(sb: Client, *, record_id: str, patch: Dict[str, Any]) -> None:
    sb.table("reach_records").update(patch).eq("id", record_id).execute()


def delete_records(sb: Client, *, record_ids: List[str]) -> int:
    if not record_ids:
        return 0
    resp = sb.table("reach_records").delete().in_("id", record_ids).execute()
    return len(resp.data or [])


def list_totals(sb: Client, *, limit: int = 5000) -> List[Dict[str, Any]]:
    resp = sb.table("reach_totals").select("*").order("cas_number", desc=False).limit(limit).execute()
    return resp.data or []


def list_totals_yearly(sb: Client, *, year: int, limit: int = 5000) -> List[Dict[str, Any]]:
    resp = (
        sb.table("reach_totals_yearly")
        .select("*")
        .eq("year", year)
        .order("cas_number", desc=False)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def list_years(sb: Client, *, limit: int = 50) -> List[int]:
    resp = sb.table("reach_years").select("year").limit(limit).execute()
    years = []
    for r in resp.data or []:
        y = r.get("year")
        if y is None:
            continue
        try:
            years.append(int(y))
        except Exception:
            continue
    years = sorted(set(years))
    return years

