from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


# Canonical column keys we'll use internally
CANONICAL_COLS = {
    "destination": {
        "destination",
        "destination / branch",
        "destination/branch",
        "destination branch",
        "branch",
        "dest",
        "الوجهة",
        "الفرع",
    },
    "state": {"state", "origin state", "ولاية", "الولاية"},
    "city": {"city", "origin city", "مدينة", "المدينة"},
    "auction_location": {
        "auction location",
        "auction",
        "auction house",
        "provider",
        "المزاد",
        "موقع المزاد",
    },
    "shipping_line": {"shipping line", "line", "carrier", "شركة الشحن", "الخط الملاحي"},
    "price_omr": {
        "price / omr",
        "price",
        "price omr",
        "omr",
        "السعر",
        "سعر الشحن",
        "السعر / omر",
        "السعر / ريال",
    },
}


# Minimal US state mapping to support code/full-name equivalence
US_STATE_ABBR_TO_NAME: Dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
US_STATE_NAME_TO_ABBR: Dict[str, str] = {v.lower(): k for k, v in US_STATE_ABBR_TO_NAME.items()}


def _norm_text(value: object) -> str:
    try:
        return str(value or "").strip()
    except Exception:
        return ""


def _norm_key(value: object) -> str:
    return _norm_text(value).lower()


def _normalize_state_name(text: str) -> str:
    """Normalize state: map 2-letter code to full name; return lowercase."""
    t = _norm_key(text)
    if not t:
        return t
    if len(t) == 2 and t.isalpha():
        # map code to name if possible
        name = US_STATE_ABBR_TO_NAME.get(t.upper())
        return name.lower() if name else t
    # if it's a full name, keep lowercase as-is
    return t


def _build_rename_map(columns: Iterable[object]) -> Dict[object, str]:
    rename: Dict[object, str] = {}
    for original in columns:
        key = _norm_key(original)
        for canon, variants in CANONICAL_COLS.items():
            if key in variants:
                rename[original] = canon
                break
    return rename


def _coerce_price_to_decimal(value: object) -> Decimal:
    s = _norm_text(value)
    # Keep digits and dot only; do not round
    cleaned = []
    for ch in s:
        if ch.isdigit() or ch == ".":
            cleaned.append(ch)
    try:
        return Decimal("".join(cleaned) or "0")
    except Exception:
        return Decimal("0")


def _ensure_required_columns(df: pd.DataFrame) -> None:
    required = ["destination", "state", "city", "auction_location", "shipping_line", "price_omر"]
    # accept both price_omr and price_omر (arabic r)
    cols_lower = [str(c).lower() for c in df.columns]
    if "price_omr" in cols_lower and "price_omر" not in cols_lower:
        # unify key to price_omr
        df.rename(columns={df.columns[cols_lower.index("price_omر")]: "price_omr"} if "price_omر" in cols_lower else {}, inplace=True)
    required = ["destination", "state", "city", "auction_location", "shipping_line", "price_omr"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")


def _read_excel_or_csv(data: bytes, filename: str) -> pd.DataFrame:
    name_lower = (filename or "").lower()
    if name_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data))
    if df is None or df.empty:
        return pd.DataFrame()
    rename = _build_rename_map(df.columns)
    if rename:
        df = df.rename(columns=rename)
    return df


def _read_pdf_tables(data: bytes) -> pd.DataFrame:
    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        raise RuntimeError("PDF parsing requires pdfplumber. Please install it.") from e

    frames: List[pd.DataFrame] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                # Try first 5 rows as header candidates
                for header_index in range(min(5, len(tbl) - 1)):
                    header = tbl[header_index]
                    if not header:
                        continue
                    rename = _build_rename_map(header)
                    # we need at least core columns present in header
                    has_core = all(any(h for h in header if _norm_key(h) in CANONICAL_COLS[k]) for k in ("destination", "state", "city", "auction_location", "price_omr"))
                    if not rename and not has_core:
                        continue
                    body = tbl[header_index + 1 :]
                    try:
                        df = pd.DataFrame(body, columns=header)
                    except Exception:
                        # Fallback: align rows length to header
                        normalized_rows = []
                        for r in body:
                            if len(r) < len(header):
                                r = list(r) + [None] * (len(header) - len(r))
                            elif len(r) > len(header):
                                r = r[: len(header)]
                            normalized_rows.append(r)
                        df = pd.DataFrame(normalized_rows, columns=header)
                    if not df.empty:
                        if rename:
                            df = df.rename(columns=rename)
                        frames.append(df)
                    break  # stop trying other header rows for this table
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def parse_document_to_dataframe(data: bytes, filename: str) -> pd.DataFrame:
    """Parse PDF/XLSX/CSV into a normalized DataFrame with canonical columns.

    Columns ensured: destination, state, city, auction_location, shipping_line, price_omr
    """
    name_lower = (filename or "").lower()
    if name_lower.endswith((".xlsx", ".xls", ".csv")):
        df = _read_excel_or_csv(data, filename)
    elif name_lower.endswith(".pdf"):
        df = _read_pdf_tables(data)
    else:
        # Try excel reader by default
        df = _read_excel_or_csv(data, filename)

    if df is None or df.empty:
        raise ValueError("No table data found in the document.")

    # Normalize column names if not already done
    rename = _build_rename_map(df.columns)
    if rename:
        df = df.rename(columns=rename)

    # Keep only relevant columns if present; do not drop others to avoid losing context
    _ensure_required_columns(df)

    # Trim whitespace
    for col in ("destination", "state", "city", "auction_location", "shipping_line"):
        df[col] = df[col].map(_norm_text)

    # Create normalized helper columns for matching (not exposed to users)
    df["_destination_key"] = df["destination"].map(_norm_key)
    df["_state_key"] = df["state"].map(_normalize_state_name)
    df["_state_raw_key"] = df["state"].map(_norm_key)
    df["_city_key"] = df["city"].map(_norm_key)
    df["_auction_key"] = df["auction_location"].map(_norm_key)

    # Keep a decimal copy of price for stable sorting/comparison; keep original for output
    df["_price_decimal"] = df["price_omr"].map(_coerce_price_to_decimal)

    return df


@dataclass
class QueryCriteria:
    destination: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    auction_location: Optional[str] = None


def _norm_optional(v: Optional[str]) -> str:
    return _norm_key(v) if v is not None else ""


def query_prices(df: pd.DataFrame, criteria: QueryCriteria) -> Tuple[pd.DataFrame, bool]:
    """Filter DataFrame by criteria.

    Returns (result_df, is_exact_match)
    """
    dest_key = _norm_optional(criteria.destination)
    state_key = _normalize_state_name(criteria.state or "")
    # also keep raw input to match possible abbreviations in file
    state_raw_key = _norm_optional(criteria.state)
    city_key = _norm_optional(criteria.city)
    auction_key = _norm_optional(criteria.auction_location)

    mask = pd.Series([True] * len(df))
    if dest_key:
        mask &= (df["_destination_key"] == dest_key)
    if state_key:
        mask &= ((df["_state_key"] == state_key) | (df["_state_raw_key"] == state_raw_key))
    if city_key:
        mask &= (df["_city_key"] == city_key)
    if auction_key:
        mask &= (df["_auction_key"] == auction_key)

    exact_df = df[mask]
    if not exact_df.empty:
        # Sort by price ascending for convenience; keep numeric precision
        exact_df = exact_df.sort_values(by=["_price_decimal", "destination", "state", "city"]).reset_index(drop=True)
        return exact_df, True

    # Partial matching with scoring
    scores: List[int] = []
    for _, row in df.iterrows():
        score = 0
        if state_key:
            if row["_state_key"] == state_key or row["_state_raw_key"] == state_raw_key:
                score += 2
            elif state_raw_key and state_raw_key in (row["_state_key"] or ""):
                score += 1
        if city_key:
            if row["_city_key"] == city_key:
                score += 2
            elif city_key in (row["_city_key"] or ""):
                score += 1
        if dest_key:
            if row["_destination_key"] == dest_key:
                score += 1
            elif dest_key in (row["_destination_key"] or ""):
                score += 1
        if auction_key:
            if row["_auction_key"] == auction_key:
                score += 1
            elif auction_key in (row["_auction_key"] or ""):
                score += 1
        scores.append(score)

    df = df.copy()
    df["_score"] = scores
    partial = df[df["_score"] > 0].sort_values(by=["_score", "_price_decimal"], ascending=[False, True]).reset_index(drop=True)
    return partial, False


def results_table(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["destination", "state", "city", "auction_location", "shipping_line", "price_omر"]
    # normalize to price_omr if present
    if "price_omر" in df.columns and "price_omr" not in df.columns:
        df = df.rename(columns={"price_omر": "price_omr"})
    cols = ["destination", "state", "city", "auction_location", "shipping_line", "price_omr"]
    present = [c for c in cols if c in df.columns]
    return df[present].copy()
