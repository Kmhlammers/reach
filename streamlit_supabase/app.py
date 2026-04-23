import hashlib
import json
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from reach.parser import parse_workbook_bytes
from reach.supabase_store import (
    create_file_row,
    delete_file,
    delete_records,
    get_supabase_client,
    insert_issues,
    list_files,
    list_records,
    list_totals,
    list_totals_yearly,
    list_years,
    update_record,
    upsert_records,
)

st.set_page_config(page_title="REACH Processor", layout="wide")

st.title("REACH Processor")
st.caption("Upload files, manage entries, and see totals (Supabase).")

sb = get_supabase_client()

tab_upload, tab_summary, tab_totals = st.tabs(["Upload & Files", "REACHSUMMARY", "Totals"])


def _date_only(value: Any) -> str:
    s = str(value or "")
    return s.split("T", 1)[0] if "T" in s else s[:10]


def _coerce_patch(row: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "sheet",
        "supplier_name",
        "supplier_name_original",
        "cas_number",
        "substance",
        "or_registered",
        "total_kg",
        "total_tonnes",
        "import_status",
        "import_message",
    }
    return {k: row.get(k) for k in allowed if k in row}


def _style_kg_red(df: pd.DataFrame, *, kg_col: str = "total_kg") -> "pd.io.formats.style.Styler":
    def _fmt(v: Any) -> str:
        try:
            return "background-color: #ffcccc;" if float(v) > 1000 else ""
        except Exception:
            return ""

    return df.style.map(_fmt, subset=[kg_col])


def _kg_column_config(*, kg_col: str = "total_kg") -> Dict[str, Any]:
    # Force enough width so 4+ digit kg values don't get clipped.
    return {
        kg_col: st.column_config.NumberColumn(
            kg_col,
            format="%.3f",
            width="medium",
        )
    }


def _autosave_key(sha256: str) -> str:
    return f"autosaved:{sha256}"


with tab_upload:
    st.subheader("Upload")
    uploaded = st.file_uploader("Upload Excel file", type=["xlsx"])
    if uploaded:
        file_bytes = uploaded.getvalue()
        file_sha256 = hashlib.sha256(file_bytes).hexdigest()

        payload: Dict[str, Any] = {"source_type": "upload", "source_ref": None, "file_name": uploaded.name}

        with st.spinner("Parsing workbook..."):
            parsed = parse_workbook_bytes(file_bytes, payload)

        if not parsed.get("ok"):
            st.error("Parsing failed.")
        else:
            st.subheader("Records preview")
            st.dataframe(parsed["records"], use_container_width=True, height=380)
            if parsed["issues"]:
                st.subheader("Issues")
                st.dataframe(parsed["issues"], use_container_width=True, height=220)

            st.download_button(
                "Download parsed JSON",
                data=json.dumps(parsed, indent=2, default=str).encode("utf-8"),
                file_name=f"{uploaded.name}.parsed.json",
                mime="application/json",
            )

            if not st.session_state.get(_autosave_key(file_sha256), False):
                try:
                    with st.spinner("Auto-saving to Supabase..."):
                        file_id = create_file_row(
                            sb,
                            source_type="upload",
                            source_ref=None,
                            file_name=uploaded.name,
                            file_sha256=file_sha256,
                            notes=None,
                        )
                        written, attempted = upsert_records(sb, file_id=file_id, records=parsed["records"])
                        issues_written = insert_issues(sb, file_id=file_id, issues=parsed["issues"])
                    st.session_state[_autosave_key(file_sha256)] = True
                    st.success(
                        f"Auto-saved. file_id={file_id}. Records written: {written} (attempted {attempted}). Issues written: {issues_written}."
                    )
                except Exception as exc:
                    st.exception(exc)
            else:
                st.info("Already auto-saved this file in this session.")

    st.divider()
    st.subheader("Uploaded files")

    files = list_files(sb)
    if not files:
        st.info("No files saved yet.")
    else:
        cards_per_row = 3
        for i in range(0, len(files), cards_per_row):
            row = st.columns(cards_per_row)
            for j in range(cards_per_row):
                idx = i + j
                if idx >= len(files):
                    continue
                f = files[idx]
                with row[j]:
                    with st.container(border=True):
                        st.write(f'**{f["file_name"]}**')
                        st.caption(f'{_date_only(f["created_at"])} • {f["source_type"]}')
                        with st.popover("Delete", use_container_width=True):
                            st.warning("Are you sure? This deletes the file and all its records/issues.")
                            if st.button("Yes, delete", type="primary", use_container_width=True, key=f"delete:{f['id']}"):
                                delete_file(sb, file_id=f["id"])
                                st.success("Deleted. Rerun to refresh.")


with tab_summary:
    st.subheader("REACHSUMMARY")

    files = list_files(sb)
    file_filter: Optional[str] = None
    if files:
        file_options = {"All files": None}
        for f in files:
            file_options[f'{_date_only(f["created_at"])} • {f["file_name"]} • {f["id"]}'] = f["id"]
        selected = st.selectbox("Filter by file", options=list(file_options.keys()))
        file_filter = file_options[selected]

    records = list_records(sb, file_id=file_filter, limit=2000)
    if not records:
        st.info("No entries found.")
    else:
        ordered_records: List[Dict[str, Any]] = []
        for r in records:
            # UI-only field and hide row_key from UI
            r["_delete"] = False
            r.pop("row_key", None)

            # Show date only in UI (keep actual timestamptz stored in DB)
            if "created_at" in r:
                r["created_at"] = _date_only(r["created_at"])
            if "processed_at" in r and r.get("processed_at"):
                r["processed_at"] = _date_only(r["processed_at"])

            # Order columns: key metrics first, then supplier early, keep id at end.
            preferred = [
                "cas_number",
                "substance",
                "total_kg",
                "total_tonnes",
                "supplier_name",
                "supplier_name_original",
                "sheet",
                "or_registered",
                "total_tonnes",
                "import_status",
                "import_message",
                "created_at",
                "processed_at",
                "file_id",
                "_delete",
            ]

            ordered: Dict[str, Any] = {}
            for k in preferred:
                if k in r and k != "id" and k not in ordered:
                    ordered[k] = r.get(k)

            for k, v in r.items():
                if k == "id" or k in ordered:
                    continue
                ordered[k] = v

            if "id" in r:
                ordered["id"] = r.get("id")
            ordered_records.append(ordered)

        edit_mode = st.toggle("Edit mode", value=False, help="Editing disables per-cell styling in Streamlit tables.")

        if not edit_mode:
            view_df = pd.DataFrame(ordered_records)
            if "total_kg" in view_df.columns:
                st.dataframe(
                    _style_kg_red(view_df, kg_col="total_kg"),
                    use_container_width=True,
                    height=640,
                    column_config=_kg_column_config(kg_col="total_kg"),
                )
            else:
                st.dataframe(view_df, use_container_width=True, height=640)
        else:
            st.caption("Edit cells, then click “Save changes”. Mark rows with Delete=true to remove them.")
            edited = st.data_editor(
                ordered_records,
                use_container_width=True,
                height=560,
                disabled=["id", "created_at", "file_id", "processed_at"],
                column_config={"_delete": st.column_config.CheckboxColumn("Delete")},
                key="reachsummary_editor",
            )

            if st.button("Save changes", type="primary"):
                original_by_id = {r["id"]: r for r in ordered_records if r.get("id")}
                edited_by_id = {r["id"]: r for r in edited if r.get("id")}

                to_delete: List[str] = [rid for rid, row in edited_by_id.items() if row.get("_delete") is True]
                if to_delete:
                    deleted_count = delete_records(sb, record_ids=to_delete)
                    st.success(f"Deleted {deleted_count} entries. Rerun to refresh.")
                else:
                    updated_count = 0
                    for rid, new_row in edited_by_id.items():
                        old_row = original_by_id.get(rid)
                        if not old_row:
                            continue
                        patch = _coerce_patch(new_row)
                        old_patch = _coerce_patch(old_row)
                        if patch != old_patch:
                            update_record(sb, record_id=rid, patch=patch)
                            updated_count += 1
                    st.success(f"Saved changes for {updated_count} entries. Rerun to refresh.")


with tab_totals:
    st.subheader("Totals per CAS")
    st.caption("Calculated by Supabase from all saved records (view: `reach_totals`).")

    all_totals = list_totals(sb, limit=5000)
    years = list_years(sb)
    year_choice = st.selectbox("Year", options=["All years"] + [str(y) for y in years], index=0)

    if year_choice != "All years":
        totals = list_totals_yearly(sb, year=int(year_choice), limit=5000)
    else:
        totals = all_totals
    if not totals:
        st.info("No totals yet (no records saved).")
    else:
        search = st.text_input("Search (CAS or substance)", placeholder="e.g. 64-17-5 or ethanol")
        if search:
            s = search.strip().lower()
            totals = [
                t
                for t in totals
                if s in str(t.get("cas_number", "")).lower() or s in str(t.get("substance", "")).lower()
            ]

        ordered = [
            {
                **({"year": t.get("year")} if year_choice != "All years" else {}),
                "cas_number": t.get("cas_number"),
                "substance": t.get("substance"),
                "total_kg": t.get("total_kg"),
                "total_tonnes": t.get("total_tonnes"),
                "record_count": t.get("record_count"),
            }
            for t in totals
        ]
        totals_df = pd.DataFrame(ordered)
        if "total_kg" in totals_df.columns:
            st.dataframe(
                _style_kg_red(totals_df, kg_col="total_kg"),
                use_container_width=True,
                height=640,
                column_config=_kg_column_config(kg_col="total_kg"),
            )
        else:
            st.dataframe(totals_df, use_container_width=True, height=640)

