"""Address normalisation and the result-cache key (plan D4)."""

from __future__ import annotations

import hashlib
import json
import re

_UNIT = re.compile(r"(?P<pre>,\s*)?\b(?:APT|APARTMENT|UNIT|STE|SUITE)\b\.?\s*#?\s*(?P<tok>[\w-]+)|#\s*[\w-]+")
_ZIP4 = re.compile(r"\b(\d{5})-\d{4}\b")


def _drop_unit(m: re.Match[str]) -> str:
    """Strip a unit designator only when it is clearly one: after a comma, or followed by a single letter or a number.

    ``Ste Marie St`` and ``Apt St`` are street names and stay; ``Apt 2B``, ``Ste 400``, ``Unit B``, ``, Apt Rear`` go.
    """
    if m.group("tok") is None:  # a '#5' form
        return " "
    tok = m.group("tok")
    if m.group("pre") or len(tok) == 1 or any(c.isdigit() for c in tok):
        return m.group("pre") or " "
    return m.group(0)


def normalize_address(matched: str) -> str:
    """Census ``matchedAddress`` -> a stable key: upper case, unit tokens dropped, ZIP5, single spaces."""
    s = _UNIT.sub(_drop_unit, (matched or "").upper())
    s = _ZIP4.sub(r"\1", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\s*,)+", ",", s)  # a removed unit can leave ", ,"
    s = re.sub(r"\s+,", ",", s)
    return s.strip(" ,")


def cache_key(*, normalized_address: str | None, lat: float | None, lng: float | None, method: str, verify: bool,
              pipeline_version: str, solar_key: bool, anthropic_key: bool) -> str:
    """sha256 hex of ``[place, method, verify, pipeline_version, solar_key, anthropic_key]``.

    ``place`` is the normalised address, or ``ll:<lat>,<lng>`` (5 dp) when no address was geocoded.
    """
    if normalized_address is not None:
        place = normalized_address
    elif lat is not None and lng is not None:
        place = f"ll:{round(lat, 5) + 0.0:.5f},{round(lng, 5) + 0.0:.5f}"  # + 0.0: -0.0 keys like 0.0
    else:
        raise ValueError("cache_key needs a normalized address or lat and lng")
    payload = [place, method, bool(verify), pipeline_version, bool(solar_key), bool(anthropic_key)]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()
