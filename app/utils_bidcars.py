from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup


VIN_REGEX = re.compile(r"\b([A-HJ-NPR-Z\d]{17})\b", re.IGNORECASE)
LOT_REGEXES = [
    re.compile(r"/lot/(\d+)", re.IGNORECASE),
    re.compile(r"[?&](?:item|id|lot|lot_id)=(\d+)", re.IGNORECASE),
    re.compile(r"\bLot\s*#?\s*(\d{5,})\b", re.IGNORECASE),
    re.compile(r"\b(\d{6,})\b"),  # fallback: long digit sequences
]


@dataclass
class ParsedBidCars:
    ok: bool
    error: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    lot_number: Optional[str] = None
    provider: Optional[str] = None  # Copart / IAAI

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "vin": self.vin,
            "make": self.make,
            "model": self.model,
            "year": self.year,
            "lot_number": self.lot_number,
            "provider": self.provider,
        }


def _first_match(regex: re.Pattern[str], text: str) -> Optional[str]:
    m = regex.search(text or "")
    return m.group(1) if m else None


def _extract_json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and (item.get("@type") in {"Product", "Vehicle"} or "vehicleIdentificationNumber" in item):
                        return item
            elif isinstance(data, dict):
                if data.get("@type") in {"Product", "Vehicle"} or "vehicleIdentificationNumber" in data:
                    return data
        except Exception:
            continue
    return {}


def _parse_title_for_ymm(title: str) -> tuple[Optional[int], Optional[str], Optional[str]]:
    # Heuristic: titles like "2019 Toyota Camry SE ..."
    if not title:
        return None, None, None
    tokens = re.split(r"\s+|[-|–]", title.strip())
    if not tokens:
        return None, None, None
    year = None
    if re.match(r"^\d{4}$", tokens[0] or ""):
        try:
            year = int(tokens[0])
            tokens = tokens[1:]
        except Exception:
            year = None
    make = tokens[0] if tokens else None
    model = None
    if tokens:
        # model often next token(s) until a comma or end
        rest = " ".join(tokens[1:])
        model = rest.split(",")[0].strip() or None
        if model:
            # limit to reasonable length
            model = model[:80]
    return year, make, model


def parse_bidcars_url(url: str, timeout: float = 10.0) -> ParsedBidCars:
    """Fetch and parse a BidCars lot page to extract VIN, lot, Y/M/M, and provider.

    Supports URLs like bid.cars or bidcars.com that aggregate Copart/IAAI listings.
    """
    if not url or ("bid.cars" not in url and "bidcars" not in url):
        return ParsedBidCars(ok=False, error="Unsupported URL. Please provide a BidCars link.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        return ParsedBidCars(ok=False, error=f"Failed to fetch URL: {exc}")

    html = resp.text or ""
    # Prefer lxml parser if available; fallback to html.parser
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # Try JSON-LD first
    jd = _extract_json_ld(soup)

    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    lot_number: Optional[str] = None
    provider: Optional[str] = None

    # Extract VIN
    for key in ("vehicleIdentificationNumber", "vin", "sku"):
        if isinstance(jd.get(key), str) and VIN_REGEX.match(jd[key]):
            vin = jd[key].upper()
            break
    if not vin:
        # Look for common meta/data attributes
        vin_attr = soup.find(attrs={"data-vin": True})
        if vin_attr and VIN_REGEX.match(vin_attr.get("data-vin", "")):
            vin = vin_attr.get("data-vin").upper()
    if not vin:
        vin = _first_match(VIN_REGEX, html)
        if vin:
            vin = vin.upper()

    # Extract provider heuristically
    page_text_lower = html.lower()
    if "copart" in page_text_lower:
        provider = "Copart"
    if "iaai.com" in page_text_lower or ">iaai<" in page_text_lower or "insurance auto auctions" in page_text_lower:
        provider = "IAAI"

    # Extract lot number from URL or page
    for rx in LOT_REGEXES:
        lot_number = _first_match(rx, url)
        if lot_number:
            break
    if not lot_number:
        # Try page content near "Lot"
        lot_number = _first_match(LOT_REGEXES[2], html) or _first_match(LOT_REGEXES[3], html)

    # Extract Year/Make/Model
    if isinstance(jd.get("brand"), dict) and isinstance(jd.get("model"), str):
        make = jd["brand"].get("name") or jd["brand"].get("brand") or make
        model = jd.get("model") or model
    name_title = jd.get("name") if isinstance(jd, dict) else None
    if not name_title:
        name_title = (soup.title.string if soup.title else None)
    y2, m2, md2 = _parse_title_for_ymm(name_title or "")
    year = year or y2
    make = make or m2
    # Prefer concise model (e.g., "Camry SE") if detected
    if md2:
        # If JSON-LD model exists and appears inside md2, keep md2; else fallback to JSON-LD model
        model = md2 if not model or (model.lower() in md2.lower()) else model

    # Normalize year
    if isinstance(jd.get("productionDate"), (int, str)):
        try:
            yval = int(str(jd.get("productionDate"))[:4])
            if 1900 <= yval <= 2100:
                year = year or yval
        except Exception:
            pass

    try:
        y_int = int(year) if year is not None else None
    except Exception:
        y_int = None

    return ParsedBidCars(
        ok=True,
        vin=vin,
        make=make,
        model=model,
        year=y_int,
        lot_number=lot_number,
        provider=provider,
    )
