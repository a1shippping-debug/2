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
        elif key in {
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
        }:
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
