"""The identity provider's display name, cleaned for an app's ``apply_profile`` hook. Stdlib only."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

NAME_MAX = 256  # Entra's displayName maximum

_KEEP = "\u200c\u200d\u200e\u200f"  # ZWNJ, ZWJ, LRM, RLM: legitimate in names (Persian, Indic, direction marks)
_DROP = frozenset({"Cc", "Cs", "Co", "Cf"})  # U+2028/2029 (Zl/Zp) are already spaces after ``split()``


@dataclass(frozen=True)
class IdentityProfile:
    """What the identity provider said about the person. ``name`` is normalised and never empty."""

    name: str


class ProfileHookError(RuntimeError):
    """An app's ``apply_profile`` raised; wrapped so the error is never read as a sign-in refusal."""


def normalize_name(value: Any) -> str | None:
    """Collapse whitespace, drop control, surrogate, private-use and format characters (bidi overrides, zero-width
    space, soft hyphen, tags; ZWNJ, ZWJ, LRM, RLM are kept), cap at ``NAME_MAX``. Unassigned code points are kept
    (they may be newer letters). None unless a letter or digit remains."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    text = " ".join("".join(c for c in text if c in _KEEP or unicodedata.category(c) not in _DROP).split())
    text = text[:NAME_MAX].rstrip(" " + _KEEP)  # a cut can leave a space or a dangling joiner
    return text if any(unicodedata.category(c)[0] in "LN" for c in text) else None


def profile_of(identity: Any) -> IdentityProfile | None:
    """The profile of an ``OidcIdentity``, or None when it carries no usable display name."""
    name = normalize_name(getattr(identity, "name", None))
    return IdentityProfile(name) if name else None
