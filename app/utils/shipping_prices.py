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
        # effective dates aliases
        eff_from_keys = {
            "effective_from",
            "from",
            "start",
            "start date",
            "effective date",
            "valid from",
            "بداية السريان",
            "تاريخ البداية",
            "effectivefrom",
            "startdate",
            "validfrom",
        }
        eff_to_keys = {
            "effective_to",
            "to",
            "end",
            "end date",
            "valid to",
            "نهاية السريان",
            "تاريخ النهاية",
            "effectiveto",
            "enddate",
            "validto",
        }

        if key in region_code_keys or simple in region_code_keys:
            rename_map[col] = "region_code"
        elif key in region_name_keys or simple in region_name_keys:
            rename_map[col] = "region_name"
        elif key in price_keys or simple in price_keys:
            rename_map[col] = "price_omr"
        elif key in eff_from_keys or simple in eff_from_keys:
            rename_map[col] = "effective_from"
        elif key in eff_to_keys or simple in eff_to_keys:
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
