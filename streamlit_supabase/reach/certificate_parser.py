import io
import re
from typing import Any, Dict, List, Optional, Tuple

from reach.parser import (
    KNOWN_SUPPLIERS,
    is_valid_cas_number,
    normalize_cas_number,
    normalize_supplier_name,
)

CAS_PATTERN = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

PARAFFIN_CAS_NUMBERS = {
    "8002-74-2",
    "64742-45-6",
    "64742-43-4",
    "64742-48-9",
}

# Literal phrases that may appear inside certificate PDF body text
SUPPLIER_TEXT_ALIASES: List[Tuple[str, str]] = [
    ("绍兴瑞耀贸易", "SHAOXING RUIYAO TRADING CO.,LTD"),
    ("绍兴瑞耀", "SHAOXING RUIYAO TRADING CO.,LTD"),
    ("SHAOXING RUIYAO TRADING CO.,LTD", "SHAOXING RUIYAO TRADING CO.,LTD"),
    ("SHAOXING RUIYAO TRADING", "SHAOXING RUIYAO TRADING CO.,LTD"),
    ("SHAOXING HIKING CANDLE GIFTS CO.,LTD", "SHAOXING HIKING CANDLE GIFTS CO.,LTD"),
    ("SHAOXING HIKING CANDLE", "SHAOXING HIKING CANDLE GIFTS CO.,LTD"),
    ("JINHUA JUSHI TECHNOLOGY CO.,LTD", "JINHUA JUSHI TECHNOLOGY CO.,LTD"),
    ("JINHUA JUSHI", "JINHUA JUSHI TECHNOLOGY CO.,LTD"),
]

_GENERIC_SUPPLIER_TOKENS = frozenset(
    {
        "ltd",
        "co",
        "inc",
        "the",
        "and",
        "limited",
        "corporation",
        "import",
        "export",
        "trading",
        "company",
        "group",
        "native",
        "produce",
    }
)


def _extract_with_pdfplumber(file_bytes: bytes) -> str:
    import pdfplumber

    parts: List[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _extract_with_pymupdf(file_bytes: bytes) -> str:
    try:
        import fitz
    except ImportError:
        return ""

    parts: List[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _extract_with_ocr(file_bytes: bytes) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        return ""

    try:
        images = convert_from_bytes(file_bytes, dpi=200)
    except Exception:
        return ""

    parts: List[str] = []
    for image in images:
        try:
            parts.append(pytesseract.image_to_string(image, lang="chi_sim+eng"))
        except Exception:
            try:
                parts.append(pytesseract.image_to_string(image, lang="eng"))
            except Exception:
                continue
    return "\n".join(parts)


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, str]:
    """Extract text from inside the PDF only."""
    try:
        text = _extract_with_pdfplumber(file_bytes)
        if text.strip():
            return text, "pdfplumber"
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for certificate PDF parsing.") from exc

    text = _extract_with_pymupdf(file_bytes)
    if text.strip():
        return text, "pymupdf"

    text = _extract_with_ocr(file_bytes)
    if text.strip():
        return text, "ocr"

    return "", "none"


def extract_cas_numbers(text: str) -> List[str]:
    found: List[str] = []
    seen: set[str] = set()
    for match in CAS_PATTERN.finditer(text):
        cas = normalize_cas_number(match.group(1))
        if is_valid_cas_number(cas) and cas not in seen:
            seen.add(cas)
            found.append(cas)
    return found


def _supplier_tokens(known: str) -> List[str]:
    return [
        t
        for t in re.findall(r"[a-zA-Z]{4,}", known.lower())
        if t not in _GENERIC_SUPPLIER_TOKENS
    ]


def _supplier_appears_in_text(known: str, text: str) -> bool:
    """Strict check: supplier name must actually appear in PDF text."""
    if known.lower() in text.lower():
        return True

    tokens = _supplier_tokens(known)
    if not tokens:
        return False

    lower = text.lower()
    hits = sum(1 for t in tokens if t in lower)
    if len(tokens) >= 2:
        return hits >= 2
    return len(tokens[0]) >= 8 and tokens[0] in lower


def guess_supplier_from_text(text: str) -> Tuple[str, str, bool]:
    """Detect supplier from PDF body text only (never from filename)."""
    if not text.strip():
        return "", "", False

    for needle, supplier in sorted(SUPPLIER_TEXT_ALIASES, key=lambda x: -len(x[0])):
        if needle in text:
            return supplier, supplier, True

    for known in KNOWN_SUPPLIERS:
        if _supplier_appears_in_text(known, text):
            return known, known, True

    return "", "", False


def _supplier_matches(record_supplier: str, matched_supplier: str) -> bool:
    rec_norm = normalize_supplier_name(record_supplier)
    sup_norm = normalize_supplier_name(matched_supplier)
    if not rec_norm or not sup_norm:
        return False
    return rec_norm == sup_norm or sup_norm in rec_norm


def _pick_single_record(candidates: List[Dict[str, Any]]) -> Optional[str]:
    if not candidates:
        return None
    if len(candidates) == 1:
        return str(candidates[0]["id"])

    without_cert = [r for r in candidates if not r.get("certificate_added")]
    pool = without_cert or candidates
    pool = sorted(pool, key=lambda r: float(r.get("total_kg") or 0), reverse=True)
    return str(pool[0]["id"])


def _select_one_record(
    records: List[Dict[str, Any]],
    *,
    supplier_matched: str,
    cas_numbers: List[str],
) -> Tuple[Optional[str], str]:
    supplier_rows = [
        r
        for r in records
        if r.get("id") and _supplier_matches(str(r.get("supplier_name") or ""), supplier_matched)
    ]
    if not supplier_rows:
        return None, "Supplier found in PDF but no matching rows in database."

    if cas_numbers:
        for cas in cas_numbers:
            cas_rows = [
                r
                for r in supplier_rows
                if normalize_cas_number(str(r.get("cas_number") or "")) == cas
            ]
            if cas_rows:
                chosen = _pick_single_record(cas_rows)
                if chosen:
                    note = f"Matched to one row (supplier + CAS {cas})."
                    if len(cas_rows) > 1:
                        note += f" Picked 1 of {len(cas_rows)} candidates with same supplier/CAS."
                    return chosen, note
        return None, f"Supplier in PDF but no row with CAS {', '.join(cas_numbers)}."

    if len(supplier_rows) == 1:
        return str(supplier_rows[0]["id"]), "Matched to the only row for this supplier."

    return None, (
        f"Supplier in PDF matches {len(supplier_rows)} rows and no CAS in PDF — "
        "cannot pick a single row. Add CAS to the certificate or narrow data."
    )


def match_pdf_to_records(
    file_bytes: bytes,
    file_name: str,
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    text, extraction_method = extract_text_from_pdf(file_bytes)
    cas_numbers = extract_cas_numbers(text)
    _, supplier_matched, supplier_found = guess_supplier_from_text(text)

    matched_record_ids: List[str] = []
    unmatched_cas: List[str] = []
    match_note = ""

    if not text.strip():
        match_note = (
            "Could not read text inside the PDF. "
            "For scanned certificates install Tesseract OCR (chi_sim + eng) and poppler."
        )
    elif not supplier_found:
        match_note = "No known supplier name found inside the PDF. No rows updated."
    else:
        chosen_id, match_note = _select_one_record(
            records,
            supplier_matched=supplier_matched,
            cas_numbers=cas_numbers,
        )
        if chosen_id:
            matched_record_ids = [chosen_id]
        if cas_numbers and not chosen_id:
            for cas in cas_numbers:
                has_row = any(
                    normalize_cas_number(str(r.get("cas_number") or "")) == cas
                    and _supplier_matches(str(r.get("supplier_name") or ""), supplier_matched)
                    for r in records
                )
                if not has_row:
                    unmatched_cas.append(cas)
        elif cas_numbers and chosen_id:
            unmatched_cas = [
                cas
                for cas in cas_numbers
                if normalize_cas_number(cas)
                != normalize_cas_number(
                    str(
                        next(
                            (r.get("cas_number") for r in records if str(r.get("id")) == chosen_id),
                            "",
                        )
                    )
                )
            ]

    return {
        "ok": True,
        "file_name": file_name,
        "extracted_cas": cas_numbers,
        "paraffin_cas_in_pdf": [c for c in cas_numbers if c in PARAFFIN_CAS_NUMBERS],
        "supplier_matched": supplier_matched,
        "supplier_found": supplier_found,
        "matched_record_ids": matched_record_ids,
        "unmatched_cas": unmatched_cas,
        "text_preview": (text[:500] + "...") if len(text) > 500 else text,
        "has_text": bool(text.strip()),
        "extraction_method": extraction_method,
        "match_note": match_note,
    }
