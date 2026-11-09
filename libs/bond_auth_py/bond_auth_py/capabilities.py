"""Capability checks behind a small policy seam.

Authority is the app's database, re-read per request; these helpers answer "does this set of capabilities
include X" for claims, a list of strings, or a role name. Apps pick a policy and pass it where they check.
"""

from collections.abc import Iterable, Mapping
from typing import Protocol

from bond_auth_py.tokens import Claims


class CapabilityPolicy(Protocol):
    def has(self, claims_or_capabilities, cap: str) -> bool: ...


def _held(source) -> list[str]:
    """The strings a source holds: ``Claims``, a mapping with ``capabilities``, a single string, or an iterable."""
    if source is None:
        return []
    if isinstance(source, Claims):
        return list(source.capabilities)
    if isinstance(source, Mapping):
        return [str(c) for c in (source.get("capabilities") or [])]
    if isinstance(source, str):
        return [source]
    return [str(c) for c in source]


class ClaimListPolicy:
    """Default: membership in the capability list. ``superuser`` (optional) is a capability that passes every check."""

    def __init__(self, superuser: str | None = None):
        self.superuser = superuser

    def has(self, claims_or_capabilities, cap: str) -> bool:
        held = _held(claims_or_capabilities)
        return cap in held or (self.superuser is not None and self.superuser in held)


class RolePolicy:
    """Roles map to capability sets (``{"admin": {"read", "write"}, "viewer": {"read"}}``).

    The held strings are role names (a ``role`` claim, or a ``Claims.capabilities`` list of roles); a capability
    passes when any held role grants it. A held string that is itself the capability also passes."""

    def __init__(self, mapping: Mapping[str, Iterable[str]]):
        self.mapping = {role: frozenset(caps) for role, caps in mapping.items()}

    def capabilities_of(self, claims_or_capabilities) -> frozenset[str]:
        out: set[str] = set()
        for role in _held(claims_or_capabilities):
            out.update(self.mapping.get(role, ()))
        return frozenset(out)

    def has(self, claims_or_capabilities, cap: str) -> bool:
        return cap in self.capabilities_of(claims_or_capabilities) or cap in _held(claims_or_capabilities)


def has(claims_or_capabilities, cap: str, policy: CapabilityPolicy | None = None) -> bool:
    return (policy or ClaimListPolicy()).has(claims_or_capabilities, cap)


def has_any(claims_or_capabilities, *caps: str, policy: CapabilityPolicy | None = None) -> bool:
    """True when any of ``caps`` passes; with no ``caps``, true (any authenticated caller)."""
    if not caps:
        return True
    return any(has(claims_or_capabilities, cap, policy) for cap in caps)
