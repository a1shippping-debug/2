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
    # Pricing category for this row. Defaults to 'normal'.
    category: str = "normal"


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
    # Deprecated: effective date fields removed
    return None


def _norm_key(value: object) -> str:
    """Lowercase, trim, and normalize basic whitespace for header matching."""
    try:
        text = str(value).replace("\u00A0", " ")  # convert NBSP to space
    except Exception:
        return ""
    return text.strip().lower()


def _simplify_key(value: object) -> str:
    """Aggressive normalization: remove non-alphanumeric to match variants like 'Region Code' -> 'regioncode'.

    This preserves Unicode letters (e.g., Arabic), and removes spaces, punctuation, and symbols.
    """
    k = _norm_key(value)
    return "".join(ch for ch in k if ch.isalnum())


def _norm_category(value: object, default: str = "normal") -> str:
    """Normalize category to one of: normal, container, vip, vvip.

    Accepts English/Arabic variants and case-insensitive values.
    """
    try:
        txt = str(value or "").strip().lower()
    except Exception:
        txt = ""
    if not txt:
        return default
    # Arabic and English synonyms
    mapping = {
        "normal": "normal",
        "عادي": "normal",
        "عاديه": "normal",
        "عادى": "normal",
        "container": "container",
        "بالحاوية": "container",
        "حاوية": "container",
        "حاويه": "container",
        "vip": "vip",
        "فيب": "vip",
        "vvip": "vvip",
        "فف أي بي": "vvip",
        "ففايبي": "vvip",
    }
    # basic cleanup for separators/spaces
    cleaned = txt.replace("-", " ").replace("_", " ").replace("/", " ").strip()
    if cleaned in mapping:
        return mapping[cleaned]
    # tolerate uppercase
    if cleaned.upper() in {"VIP", "VVIP"}:
        return cleaned.lower()
    # numeric mapping if users send codes
    if cleaned in {"0", "1", "2", "3"}:
        return ["normal", "container", "vip", "vvip"][int(cleaned)]
    # default fallback
    return default


def _maybe_promote_first_row_to_header(df: pd.DataFrame) -> pd.DataFrame:
    """If columns look like generic/unnamed and first row contains header labels,
    use the first row as the new header and drop it from data.

    This is common when Excel exports have headers in the first data row, leaving
    pandas to assign "Unnamed: x" column names.
    """
    try:
        cols = [str(c) for c in df.columns]
        looks_unnamed = all(c.lower().startswith("unnamed:") for c in cols)
        if not looks_unnamed or df.empty:
            return df

        first = df.iloc[0].fillna("")
        header_candidates = { _norm_key(v) for v in first.tolist() }
        # Any of these signals likely indicates a header row
        signals = {
            "region_name", "region_code", "price_omr", "price / omr",
            "state", "city", "auction location", "shipping line",
            "destination", "code", "رمز", "الرمز", "السعر",
        }
        if header_candidates & signals:
            # promote
            new_cols = []
            for v in first.tolist():
                key = str(v).strip()
                new_cols.append(key if key else "")
            df2 = df.iloc[1:].copy()
            # Ensure unique column names if duplicates exist
            seen = {}
            uniq_cols: list[str] = []
            for c in new_cols:
                base = c or ""
                if base not in seen:
                    seen[base] = 1
                    uniq_cols.append(base)
                else:
                    seen[base] += 1
                    uniq_cols.append(f"{base}_{seen[base]}")
            df2.columns = uniq_cols
            return df2
    except Exception:
        pass
    return df


def _abbr_auction_location(text: str) -> str:
    t = _norm_key(text)
    if not t:
        return ""
    if "crashedtoys" in t:
        return "CT"
    if "copart" in t:
        return "CP"
    if " iaa" in f" {t}" or t.startswith("iaa"):
        return "IAA"
    if "manheim" in t:
        return "MH"
    if "ace" in t:
        return "ACE"
    # default: take first letters of up to 3 words
    parts = [p for p in text.strip().split() if p]
    if not parts:
        return ""
    return "".join(p[0] for p in parts[:3]).upper()


def _make_region_code(state_code: str | None, city: str | None, auction_location: str | None, max_len: int = 50) -> str:
    sc = (state_code or "").strip().upper()
    city_part = (city or "").strip().replace(" ", "").upper()
    if len(city_part) > 12:
        city_part = city_part[:12]
    auc_abbr = _abbr_auction_location(auction_location or "")
    parts = [p for p in [sc, city_part, auc_abbr] if p]
    code = "-".join(parts) if parts else (city_part or auc_abbr or sc or "REG")
    # hard trim to max_len
    if len(code) > max_len:
        code = code[:max_len]
    return code


def parse_shipping_prices_file(data: bytes, filename: str) -> List[ShippingRegionRow]:
    """
    Parse CSV/XLSX content and return rows.

    Expected columns (case-insensitive, Arabic or English accepted):
    - region_code | code | رمز | الرمز
    - region_name | name | المنطقة | اسم المنطقة
    - price | price_omr | السعر | سعر الشحن
    """
    name_lower = (filename or "").lower()
    if name_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data))

    # Handle files where the first data row actually contains headers
    df = _maybe_promote_first_row_to_header(df)

    # Normalize column names with robust matching and expanded aliases
    rename_map = {}
    for col in list(df.columns):
        key = _norm_key(col)
        simple = _simplify_key(col)

        # region_code aliases
        region_code_keys = {
            # direct keys
            "region_code",
            "code",
            "رمز",
            "الرمز",
            "الكود",
            "كود",
            # simplified keys (no spaces/punct)
            "regioncode",
            "codeno",
            "codenum",
            "code#",
            "codeid",
        }
        # region_name aliases (destination/name)
        region_name_keys = {
            "region_name",
            "name",
            "destination",
            "dest",
            "المنطقة",
            "اسم المنطقة",
            "اسم",
            "الوجهة",
            # simplified variants
            "regionname",
            "region",
        }
        # price/OMR aliases
        price_keys = {
            # English variants
            "price",
            "price omr",
            "price / omr",
            "price_omr",
            "omr",
            "omr price",
            "price (omr)",
            # Arabic variants
            "السعر",
            "سعر الشحن",
            "السعر / ريال",
            "السعر / omr",
            "السعر / omر",
            # simplified
            "priceomr",
        }
        # optional detailed geo columns (used to synthesize region_code)
        state_keys = {"state", "الولاية", "المنطقة", "ولاية"}
        city_keys = {"city", "المدينة", "مدينة"}
        auction_location_keys = {
            "auction location",
            "auction",
            "location",
            "مزاد",
            "موقع المزاد",
        }
        shipping_line_keys = {"shipping line", "line", "carrier", "شركة الشحن", "الخط الملاحي"}
        # category aliases
        category_keys = {
            "category",
            "الفئة",
            "التصنيف",
            "نوع",
            "نوع الشحن",
            "كاتيجوري",
            # simplified
            "categoryname",
            "cat",
        }
        # effective dates removed (ignored)

        if key in region_code_keys or simple in region_code_keys:
            rename_map[col] = "region_code"
        elif key in region_name_keys or simple in region_name_keys:
            rename_map[col] = "region_name"
        elif key in price_keys or simple in price_keys:
            rename_map[col] = "price_omr"
        # ignore effective date columns if present
        elif key in state_keys or simple in state_keys:
            rename_map[col] = "state"
        elif key in city_keys or simple in city_keys:
            rename_map[col] = "city"
        elif key in auction_location_keys or simple in auction_location_keys:
            rename_map[col] = "auction_location"
        elif key in shipping_line_keys or simple in shipping_line_keys:
            rename_map[col] = "shipping_line"
        elif key in category_keys or simple in category_keys:
            rename_map[col] = "category"

    if rename_map:
        df = df.rename(columns=rename_map)

    # If "region_code" is missing but we have detailed columns, we will synthesize it later.
    has_region_code = "region_code" in df.columns
    has_price = "price_omr" in df.columns
    if not has_price:
        raise ValueError("Missing required column: price_omr")

    rows: List[ShippingRegionRow] = []
    # Track codes to deduplicate within a single import
    seen_codes: set[str] = set()
    for _, r in df.iterrows():
        rc_raw = str(r.get("region_code", "") or "").strip()
        price = _coerce_decimal(r.get("price_omr"))
        if price is None:
            price = Decimal("0")
        # synthesize code when missing or clearly non-unique (e.g., state code only)
        state_val = (str(r.get("state", "")) or "").strip()
        city_val = (str(r.get("city", "")) or "").strip()
        auction_val = (str(r.get("auction_location", "")) or "").strip()

        code: str
        if not rc_raw or (len(rc_raw) <= 3 and (city_val or auction_val)):
            code = _make_region_code(rc_raw or state_val, city_val, auction_val)
        else:
            code = rc_raw

        # Ensure uniqueness within this file by appending numeric suffix if needed
        base = code
        suffix = 1
        while code in seen_codes:
            suffix += 1
            trial = f"{base}-{suffix}"
            code = trial[:50]
        seen_codes.add(code)

        # Build a friendly name
        reg_name = r.get("region_name")
        friendly: Optional[str] = None
        try:
            parts: list[str] = []
            if reg_name and str(reg_name).strip():
                parts.append(str(reg_name).strip())
            loc_bits = []
            if city_val:
                loc_bits.append(city_val)
            if state_val:
                loc_bits.append(state_val)
            if loc_bits:
                parts.append(", ".join(loc_bits))
            if auction_val:
                parts.append(auction_val)
            friendly = " - ".join(parts) if parts else None
        except Exception:
            friendly = None

        # effective dates dropped

        # Skip rows that still don't have a code after attempts
        if not (code or "").strip():
            continue

        # category normalization with default 'normal' if not provided
        category_val = _norm_category(r.get("category"), default="normal")

        rows.append(
            ShippingRegionRow(
                region_code=code,
                region_name=(friendly or (str(reg_name).strip() if reg_name is not None and str(reg_name).strip() else None)),
                price_omr=price,
                category=category_val,
            )
        )
    return rows
