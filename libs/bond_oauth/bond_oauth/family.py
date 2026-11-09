"""Which identity rules a provider follows: ``"google"`` (``sub``) or ``"microsoft"`` (``tid:oid``, tenant pin)."""

from __future__ import annotations

from typing import Any

FAMILIES = ("google", "microsoft")


def family_of(name: str, provider: Any = None) -> str | None:
    """The provider's ``family`` attribute; ``None`` when it is present but not a known family (refuse it).

    Only a provider with NO ``family`` attribute (a custom class from before 0.2.0) falls back to the registered NAME
    containing ``microsoft``. Real providers carry the attribute, so a Microsoft provider registered as ``entra``
    still gets Microsoft rules.
    """
    if provider is not None and hasattr(provider, "family"):
        return provider.family if provider.family in FAMILIES else None
    return "microsoft" if "microsoft" in name.lower() else "google"  # legacy fallback: the attribute is missing
