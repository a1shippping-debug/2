#!/usr/bin/env python3
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Tuple

DB_PATH = "/workspace/instance/cartrade.db"
JSON_PATH = "/workspace/scripts/shipping_prices.json"


def _to_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    try:
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        s = str(val).strip()
        if not s:
            return Decimal("0")
        # keep digits and dot only
        cleaned = []
        for ch in s:
            if ch.isdigit() or ch == ".":
                cleaned.append(ch)
        return Decimal("".join(cleaned) or "0")
    except (InvalidOperation, Exception):
        return Decimal("0")


def load_sheet(path: str):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Replace non-standard NaN tokens with null to make valid JSON
    text = text.replace(": NaN", ": null").replace(":  NaN", ": null")
    data = json.loads(text)
    sheet = data.get("Sheet1") or []
    if not sheet:
        raise RuntimeError("Sheet1 not found or empty in JSON")
    return sheet


def find_column_indices(header_row: Dict[str, Any]) -> Dict[str, str]:
    # header_row maps Unnamed:i -> Column Name
    inverse: Dict[str, str] = {}
    for k, v in header_row.items():
        name = str(v or "").strip().lower()
        inverse[name] = k
    return inverse


def aggregate_by_region(sheet: list) -> Dict[str, Tuple[Decimal, str]]:
    header = sheet[0] if sheet else {}
    name_to_key = find_column_indices(header)
    key_region_code = name_to_key.get("region_code")
    key_region_name = name_to_key.get("region_name")
    key_state = name_to_key.get("state")
    key_price = name_to_key.get("price_omr")
    if not key_region_code or not key_price:
        raise RuntimeError("JSON missing required columns: region_code or price_omr")

    best: Dict[str, Tuple[Decimal, str]] = {}  # code -> (min_price, name)

    for row in sheet[1:]:  # skip header
        try:
            code_raw = row.get(key_region_code)
            code = str(code_raw or "").strip().upper()
            if not code:
                continue
            price_raw = row.get(key_price)
            price = _to_decimal(price_raw)
            # choose a human-friendly name: prefer STATE, fallback to region_name
            name_val = None
            if key_state:
                name_val = row.get(key_state)
            if not name_val and key_region_name:
                name_val = row.get(key_region_name)
            name = str(name_val or "").strip()
            # Keep the lowest price per code
            if code not in best or price < best[code][0]:
                best[code] = (price, name)
        except Exception:
            continue
    return best


def upsert_into_sqlite(mapping: Dict[str, Tuple[Decimal, str]]):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # Ensure table exists (it should); do not modify schema
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0
        for code, (price, name) in mapping.items():
            # Use INSERT INTO ... ON CONFLICT(region_code) DO UPDATE for idempotency
            cur.execute(
                """
                INSERT INTO shipping_region_prices (region_code, region_name, price_omr, effective_from, effective_to, created_at)
                VALUES (?, ?, ?, NULL, NULL, ?)
                ON CONFLICT(region_code) DO UPDATE SET
                    region_name=excluded.region_name,
                    price_omr=excluded.price_omr
                """,
                (code, name or None, float(price), now_str),
            )
            inserted += 1
        conn.commit()
        print(f"upserted_regions={inserted}")
    finally:
        conn.close()


def main():
    sheet = load_sheet(JSON_PATH)
    mapping = aggregate_by_region(sheet)
    upsert_into_sqlite(mapping)


if __name__ == "__main__":
    main()
