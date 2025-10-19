#!/usr/bin/env python3
import argparse
import sys
from typing import Optional

import pandas as pd

# Local import
from app.utils.shipping_prices import (
    load_shipping_table_from_file,
    filter_shipping_rows,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Extract Price/OMR from shipping table by Destination/State/City/Auction/Line."
        )
    )
    p.add_argument("file", help="Path to PDF/XLSX/CSV containing the table")
    p.add_argument("--destination", "-d", help="Destination/Branch name", default=None)
    p.add_argument("--state", "-s", help="State code or full name", default=None)
    p.add_argument("--city", "-c", help="City name", default=None)
    p.add_argument("--auction", "-a", help="Auction Location (e.g., Copart, IAA, Manheim)", default=None)
    p.add_argument("--line", "-l", help="Shipping Line", default=None)
    p.add_argument(
        "--only-price",
        action="store_true",
        help="If a single exact match exists, print price only",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    ns = parse_args(argv)
    try:
        df = load_shipping_table_from_file(ns.file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    result, is_exact = filter_shipping_rows(
        df,
        destination=ns.destination,
        state=ns.state,
        city=ns.city,
        auction_location=ns.auction,
        shipping_line=ns.line,
    )

    if result.empty:
        print("No matching rows found.")
        return 1

    if ns.only_price and is_exact and len(result) == 1:
        print(str(result.iloc[0]["price_omr"]))
        return 0

    # Show compact table
    cols = [
        "destination",
        "state",
        "city",
        "auction_location",
        "shipping_line",
        "price_omr",
    ]
    print(result[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
