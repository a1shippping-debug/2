from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

import pandas as pd


@dataclass
class ShippingRegionRow:
    region_code: str
    region_name: Optional[str]
    price_omr: Decimal
    effective_from: Optional[datetime]
    effective_to: Optional[datetime]


def _coerce_decimal(value) -> Decimal:
    try:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        s = str(value).strip().replace(",", "")
        if not s:
            return Decimal("0")
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _coerce_datetime(value) -> Optional[datetime]:
    try:
        if value in (None, "", float("nan")):
            return None
    except Exception:
        pass
    try:
        if isinstance(value, datetime):
            return value
        # Let pandas parse common formats
        return pd.to_datetime(value, errors="coerce").to_pydatetime() if value else None
    except Exception:
        return None


def parse_shipping_prices_file(data: bytes, filename: str) -> List[ShippingRegionRow]:
    """
    Parse CSV/XLSX content and return rows.

    Expected columns (case-insensitive, Arabic or English accepted):
    - region_code | code | رمز | الرمز
    - region_name | name | المنطقة | اسم المنطقة
    - price | price_omr | السعر | سعر الشحن
    - effective_from | from | بداية السريان (اختياري)
    - effective_to | to | نهاية السريان (اختياري)
    """
    name_lower = (filename or "").lower()
    if name_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data))

    # Normalize column names
    rename_map = {}
    for col in list(df.columns):
        key = str(col).strip().lower()
        if key in {"region_code", "code", "رمز", "الرمز"}:
            rename_map[col] = "region_code"
        elif key in {"region_name", "name", "المنطقة", "اسم المنطقة", "اسم"}:
            rename_map[col] = "region_name"
        elif key in {"price", "price_omr", "السعر", "سعر الشحن"}:
            rename_map[col] = "price_omr"
        elif key in {"effective_from", "from", "بداية السريان", "تاريخ البداية"}:
            rename_map[col] = "effective_from"
        elif key in {"effective_to", "to", "نهاية السريان", "تاريخ النهاية"}:
            rename_map[col] = "effective_to"
    if rename_map:
        df = df.rename(columns=rename_map)

    # Required
    for required in ["region_code", "price_omr"]:
        if required not in df.columns:
            raise ValueError(f"Missing required column: {required}")

    rows: List[ShippingRegionRow] = []
    for _, row in df.iterrows():
        code = str(row.get("region_code", "")).strip()
        if not code:
            continue
        name = row.get("region_name")
        price = _coerce_decimal(row.get("price_omr"))
        eff_from = _coerce_datetime(row.get("effective_from"))
        eff_to = _coerce_datetime(row.get("effective_to"))
        rows.append(
            ShippingRegionRow(
                region_code=code,
                region_name=(str(name).strip() if name is not None and str(name).strip() else None),
                price_omr=price,
                effective_from=eff_from,
                effective_to=eff_to,
            )
        )
    return rows


# ========= Shipping table (Destination/State/City/Auction/Line/Price) =========

@dataclass
class ShippingTableRow:
    destination: str
    state: str
    city: str
    auction_location: str
    shipping_line: Optional[str]
    price_omr: str  # Keep original numeric text to avoid rounding/formatting changes


_US_STATE_CODE_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}
_US_STATE_NAME_TO_CODE = {v.lower(): k for k, v in _US_STATE_CODE_TO_NAME.items()}


def _normalize_column_key(name: str) -> str:
    key = str(name or "").strip().lower()
    key = key.replace("\\u200f", "").replace("\\u200e", "")  # remove RTL/LTR marks if present
    key_simple = key.replace(" ", "").replace("/", "").replace("-", "")

    # English and Arabic variants
    mapping = {
        # Destination / Branch
        "destination": "destination",
        "branch": "destination",
        "destinationbranch": "destination",
        "destination/branch": "destination",
        "الوجهة": "destination",
        "الفرع": "destination",
        # State
        "state": "state",
        "الولاية": "state",
        # City
        "city": "city",
        "المدينة": "city",
        # Auction Location
        "auctionlocation": "auction_location",
        "auction": "auction_location",
        "المزاد": "auction_location",
        "جهةالمزاد": "auction_location",
        # Shipping Line
        "shippingline": "shipping_line",
        "line": "shipping_line",
        "الخطالبحري": "shipping_line",
        # Price / OMR
        "price": "price_omr",
        "priceomr": "price_omr",
        "price/omr": "price_omr",
        "السعر": "price_omr",
        "سعرالشحن": "price_omr",
    }
    return mapping.get(key_simple, mapping.get(key, key))


def _normalize_value(text: Optional[str]) -> str:
    if text is None:
        return ""
    return str(text).strip()


def _load_excel_or_csv(data: bytes, filename: str) -> pd.DataFrame:
    name_lower = (filename or "").lower()
    if name_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data))
    else:
        # xlsx/xls and others supported by pandas/openpyxl
        df = pd.read_excel(io.BytesIO(data))
    return df


def _detect_and_normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("Input table is empty.")

    rename_map: dict = {}
    for col in list(df.columns):
        norm = _normalize_column_key(col)
        if norm != col:
            rename_map[col] = norm
    if rename_map:
        df = df.rename(columns=rename_map)

    required = [
        "destination",
        "state",
        "city",
        "auction_location",
        "shipping_line",
        "price_omr",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "Missing required columns: " + ", ".join(missing) +
            ". Expected: Destination/Branch, State, City, Auction Location, Shipping Line, Price / OMR"
        )

    # Clean whitespace; keep original price text exactly (trimmed)
    for c in ["destination", "state", "city", "auction_location", "shipping_line"]:
        df[c] = df[c].map(_normalize_value)
    # Price as original string trimmed; do not coerce or round
    df["price_omr"] = df["price_omr"].astype(str).map(lambda s: str(s).strip())
    return df


def _try_parse_pdf_tables(data: bytes) -> Optional[pd.DataFrame]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return None

    try:
        tables: list[pd.DataFrame] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                for tbl in page.extract_tables() or []:
                    if not tbl:
                        continue
                    # Assume first row is header; sometimes headers repeat per page
                    header = [(_normalize_column_key(h) if h is not None else "") for h in tbl[0]]
                    body = tbl[1:] if len(tbl) > 1 else []
                    if not any(h in {"destination", "state", "city", "auction_location", "price_omr"} for h in header):
                        # Try to locate header row within the first few rows
                        found_idx = None
                        for i, row in enumerate(tbl[:5]):
                            norm = [(_normalize_column_key(h) if h is not None else "") for h in row]
                            if any(h in {"destination", "state", "city", "auction_location", "price_omr"} for h in norm):
                                header = norm
                                body = tbl[i + 1 :]
                                found_idx = i
                                break
                        if found_idx is None:
                            continue
                    df = pd.DataFrame(body, columns=[h if h else f"col_{i}" for i, h in enumerate(header)])
                    tables.append(df)
        if not tables:
            return None
        df = pd.concat(tables, ignore_index=True)
        df = _detect_and_normalize_columns(df)
        # Drop rows without a price value
        df = df[df["price_omr"].astype(str).str.strip() != ""]
        return df.reset_index(drop=True)
    except Exception:
        return None


def load_shipping_table_from_file(file_path: str) -> pd.DataFrame:
    """Load a shipping table from CSV/XLSX/PDF and normalize columns.

    Raises ValueError if required columns are missing or file cannot be parsed.
    """
    with open(file_path, "rb") as f:
        data = f.read()
    name_lower = file_path.lower()
    if name_lower.endswith(".pdf"):
        df = _try_parse_pdf_tables(data)
        if df is None:
            raise ValueError(
                "Failed to parse PDF table. Install pdfplumber or convert PDF to Excel."
            )
        return df
    else:
        df = _load_excel_or_csv(data, file_path)
        df = _detect_and_normalize_columns(df)
        # Drop rows without a price value
        df = df[df["price_omr"].astype(str).str.strip() != ""]
        return df.reset_index(drop=True)


def _canonical_state_text(value: str) -> tuple[str, str]:
    """Return (state_code, state_name) best-effort from input (code or name)."""
    s = (value or "").strip()
    if not s:
        return "", ""
    upper = s.upper()
    lower = s.lower()
    if upper in _US_STATE_CODE_TO_NAME:
        return upper, _US_STATE_CODE_TO_NAME[upper]
    if lower in _US_STATE_NAME_TO_CODE:
        code = _US_STATE_NAME_TO_CODE[lower]
        return code, _US_STATE_CODE_TO_NAME[code]
    return s, s  # unknown; return as-is


def _norm_cmp(value: str) -> str:
    return (value or "").strip().lower()


def filter_shipping_rows(
    df: pd.DataFrame,
    *,
    destination: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    auction_location: Optional[str] = None,
    shipping_line: Optional[str] = None,
) -> tuple[pd.DataFrame, bool]:
    """Filter rows with exact matching first; if none, fallback to partial.

    Returns (result_df, is_exact_match).
    """
    work = df.copy()

    # Precompute normalized columns for matching
    work["_destination"] = work["destination"].map(_norm_cmp)
    work["_state"] = work["state"].map(_norm_cmp)
    work["_city"] = work["city"].map(_norm_cmp)
    work["_auction"] = work["auction_location"].map(_norm_cmp)
    work["_line"] = work["shipping_line"].map(_norm_cmp)

    dest_n = _norm_cmp(destination) if destination else None
    state_code, state_name = _canonical_state_text(state or "") if state else (None, None)
    state_norms = {s for s in {state_code, state_name} if s}  # compare against either
    city_n = _norm_cmp(city) if city else None
    auc_n = _norm_cmp(auction_location) if auction_location else None
    line_n = _norm_cmp(shipping_line) if shipping_line else None

    def apply_filters(base: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        m = pd.Series([True] * len(base))
        for k in keys:
            if k == "destination" and dest_n:
                m &= base["_destination"] == dest_n
            elif k == "state" and state_norms:
                m &= base["_state"].isin({s.lower() for s in state_norms})
            elif k == "city" and city_n:
                m &= base["_city"] == city_n
            elif k == "auction" and auc_n:
                m &= base["_auction"] == auc_n
            elif k == "line" and line_n:
                m &= base["_line"] == line_n
        return base[m]

    # Tiers for exact matching (from strict to loose)
    tiers: list[list[str]] = []
    # Build based on provided inputs only
    provided = []
    if dest_n:
        provided.append("destination")
    if state_norms:
        provided.append("state")
    if city_n:
        provided.append("city")
    if auc_n:
        provided.append("auction")
    if line_n:
        provided.append("line")
    if provided:
        tiers.append(provided)  # all provided fields
    # Partial fallbacks
    # Common useful fallbacks
    fallbacks = [
        ["city", "state"],
        ["city"],
        ["state"],
        ["destination"],
        ["auction"],
    ]
    for fb in fallbacks:
        if any(f in provided for f in fb):
            tiers.append([f for f in fb if f in {"destination", "state", "city", "auction", "line"} and (
                (f == "destination" and dest_n) or
                (f == "state" and state_norms) or
                (f == "city" and city_n) or
                (f == "auction" and auc_n) or
                (f == "line" and line_n)
            )])

    for idx, keys in enumerate(tiers):
        if not keys:
            continue
        subset = apply_filters(work, keys)
        if not subset.empty:
            result = subset[[
                "destination", "state", "city", "auction_location", "shipping_line", "price_omr"
            ]].reset_index(drop=True)
            return result, (idx == 0)

    # If nothing matched at all, return empty exact=False
    return work.iloc[0:0][[
        "destination", "state", "city", "auction_location", "shipping_line", "price_omr"
    ]], False


def rows_to_dataclasses(df: pd.DataFrame) -> List[ShippingTableRow]:
    out: List[ShippingTableRow] = []
    for _, r in df.iterrows():
        out.append(
            ShippingTableRow(
                destination=str(r.get("destination", "")),
                state=str(r.get("state", "")),
                city=str(r.get("city", "")),
                auction_location=str(r.get("auction_location", "")),
                shipping_line=(str(r.get("shipping_line")) if r.get("shipping_line") is not None else None),
                price_omr=str(r.get("price_omr", "")),
            )
        )
    return out

