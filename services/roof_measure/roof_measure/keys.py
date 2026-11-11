"""Cache and alias keys for a measurement request (plan D4)."""

from __future__ import annotations

from typing import Any

from .normalize import cache_key, normalize_address
from .settings import keys_present
from .version import PIPELINE_VERSION


def _method_slot(req: dict[str, Any]) -> str:
    """Method plus the debug inputs that change the output, so fixture jobs never collide."""
    extra = [req.get(k) for k in ("blocks_fixture", "solar_fixture", "fixture")]
    return req["method"] if not any(extra) else "|".join([req["method"], *(str(x) for x in extra)])


def _key(place: str | None, req: dict[str, Any]) -> str:
    solar, anthropic = keys_present()
    return cache_key(normalized_address=place, lat=req.get("lat"), lng=req.get("lng"), method=_method_slot(req),
                     verify=req["verify"], pipeline_version=PIPELINE_VERSION, solar_key=solar,
                     anthropic_key=anthropic)


def request_key(req: dict[str, Any]) -> str | None:
    """The final key when it is known without geocoding (coordinates or debug fixtures), else None."""
    if req.get("lat") is not None:
        return _key(None, req)
    if req.get("blocks_fixture") or req.get("fixture"):
        return _key(normalize_address(req["address"]), req)
    return None


def alias_key(req: dict[str, Any]) -> str:
    """Key of the raw input address; maps to the geocoder-based key once a job has finished."""
    return _key("in:" + normalize_address(req["address"]), req)


def matched_key(matched: str, req: dict[str, Any]) -> str:
    return _key(normalize_address(matched), req)
