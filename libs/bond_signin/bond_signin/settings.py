"""``SignInSettings``: plain dataclass, ``from_env`` for the ``BOND_SIGNIN_`` variables."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

_TRUE = ("1", "true", "yes", "on")
_WEB_SCHEMES = ("http", "https", "javascript", "data", "file", "about", "vbscript")
_REVERSE_DOMAIN = re.compile(r"[a-z][a-z0-9+.-]*")


def origin_of(url: str) -> str | None:
    """``scheme://host[:port]`` lowercased, or None for anything that is not an absolute http(s) URL."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.netloc or "\\" in url:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


@dataclass(frozen=True)
class SignInSettings:
    providers: tuple[str, ...]
    public_base: str
    redirect_allowlist: tuple[str, ...] = ()
    native_return_base: str = ""
    native_schemes: tuple[str, ...] = ()
    break_glass: bool = False
    nonce_cookie_name: str = "bond_signin"
    cookie_secure: bool = True
    delivery_web: str = "cookie"
    allow_http: bool = False
    prefix: str = "/auth"

    def __post_init__(self) -> None:
        base = (self.public_base or "").rstrip("/")
        parts = urlsplit(base)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("public_base must be an absolute URL")
        if parts.scheme != "https" and not self.allow_http:
            raise ValueError("public_base must be https (allow_http=True only for local runs)")
        if parts.scheme == "https" and not self.cookie_secure and not self.allow_http:
            raise ValueError("cookie_secure=False needs allow_http=True (local runs only)")
        for scheme in self.native_schemes:
            bare = scheme.lower().rstrip(":/")
            if bare in _WEB_SCHEMES or not _REVERSE_DOMAIN.fullmatch(bare) or "." not in bare:
                raise ValueError(f"native scheme {scheme!r} must be a reverse-domain scheme such as org.example.app")
        object.__setattr__(self, "prefix", "/" + self.prefix.strip("/"))
        object.__setattr__(self, "public_base", base)
        if not self.native_return_base:
            object.__setattr__(self, "native_return_base", f"{base}{self.prefix.rsplit('/', 1)[0]}/app/return")
        object.__setattr__(self, "native_return_base", self.native_return_base.rstrip("/"))

    @property
    def return_path_prefix(self) -> str:
        """Path prefix of the return page, e.g. ``/app/return/`` or ``/api/v1/app/return/``: for the well-known router."""
        return f"{self.prefix.rsplit('/', 1)[0]}/app/return/"

    @property
    def own_origin(self) -> str:
        return origin_of(self.public_base) or ""

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset(o for o in (origin_of(a) for a in self.redirect_allowlist) if o) | {self.own_origin}

    def callback_url(self, provider: str) -> str:
        return f"{self.public_base}{self.prefix}/signin/{provider}/callback"

    def native_scheme_ok(self, url: str) -> bool:
        scheme = urlsplit(url or "").scheme.lower()
        wanted = {s.lower().rstrip(":/") for s in self.native_schemes}
        return bool(scheme) and scheme in wanted and "\\" not in url


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(p.strip() for p in (value or "").split(",") if p.strip())


def from_env(prefix: str = "BOND_SIGNIN_", env: Mapping[str, str] | None = None) -> SignInSettings:
    """Read ``<prefix>PROVIDERS, PUBLIC_BASE, REDIRECT_ALLOWLIST, NATIVE_RETURN_BASE, NATIVE_SCHEMES, BREAKGLASS,
    COOKIE_SECURE, ALLOW_HTTP``. ``COOKIE_SECURE`` defaults to true unless ``ALLOW_HTTP`` is set."""
    source = os.environ if env is None else env

    def get(name: str) -> str | None:
        return source.get(prefix + name)

    allow_http = (get("ALLOW_HTTP") or "").lower() in _TRUE
    secure = get("COOKIE_SECURE")
    return SignInSettings(
        providers=_csv(get("PROVIDERS")), public_base=get("PUBLIC_BASE") or "",
        redirect_allowlist=_csv(get("REDIRECT_ALLOWLIST")), native_return_base=get("NATIVE_RETURN_BASE") or "",
        native_schemes=_csv(get("NATIVE_SCHEMES")), break_glass=(get("BREAKGLASS") or "").lower() in _TRUE,
        cookie_secure=(not allow_http) if secure is None else secure.lower() in _TRUE, allow_http=allow_http,
        prefix=get("PREFIX") or "/auth",
    )
