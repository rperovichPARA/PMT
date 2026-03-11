"""Shared J-Quants V2 API helpers and FX rate fetching."""

from __future__ import annotations

import os

import requests as http_requests

JQUANTS_API_KEY = os.environ.get("JQUANTS_API_KEY", "IsSPKDgnOojzoMEjBGhivJuw7_c9FBPlPDzt4iuYPdc")
JQUANTS_BASE_URL = "https://api.jquants.com/v2"


def jquants_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to J-Quants V2 API."""
    resp = http_requests.get(
        f"{JQUANTS_BASE_URL}{path}",
        headers={"x-api-key": JQUANTS_API_KEY},
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_usd_jpy_rate() -> float | None:
    """Fetch current USD/JPY rate from a public API. Returns None on failure."""
    try:
        resp = http_requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=10,
        )
        resp.raise_for_status()
        rate = resp.json().get("rates", {}).get("JPY")
        if rate and float(rate) > 1.0:
            return float(rate)
    except Exception:
        pass
    return None
