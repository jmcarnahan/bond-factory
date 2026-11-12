"""Settings read from the environment. Fake mode needs no variables at all."""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

OUT_DIR = Path("out")
FAKE_SYNC_URL = "http://localhost:8012/powersync-fake"  # fake mode: a stand-in endpoint so /sync/token can mint
DEV_SECRET = "dev-secret-change-me-dev-secret-change-me"  # >= 32 bytes so PyJWT does not warn; never use in real mode


PUBLIC_BASE = "http://localhost:8012"  # fake mode only; real mode must name its own https address
FAKE_PROVIDERS = "fake-google,fake-microsoft"
DEFAULT_SCHEME = "org.example.sdkdemo"  # sign-in schemes are reverse-domain (the lib refuses `sdkdemo`)


def _hhmm(name: str, value: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
        raise RuntimeError(f"{name} must be a time as HH:MM")
    return value


def _lead(value: str) -> int:
    if not value.isdigit() or int(value) > 10080:
        raise RuntimeError("SDK_EXAMPLE_LEAD_MINUTES must be a whole number of minutes, at most 10080")
    return int(value)


def _instant(name: str, value: str) -> datetime | None:
    """An optional ISO 8601 instant from the environment; naive UTC (a value with no offset is read as UTC)."""
    if not value:
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        raise RuntimeError(f"{name} must be an ISO 8601 date and time") from None
    return (at.replace(tzinfo=UTC) if at.tzinfo is None else at).astimezone(UTC).replace(tzinfo=None)


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _origin(url: str) -> str:
    parts = url.split("/", 3)
    return "/".join(parts[:3]).lower()  # scheme://host[:port]


def _android(value: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """`package=FINGERPRINT;FINGERPRINT,other.package=FINGERPRINT` (fingerprints are colon-separated hex)."""
    apps = []
    for entry in _split(value):
        package, _, prints = entry.partition("=")
        apps.append((package.strip(), tuple(p.strip() for p in prints.split(";") if p.strip())))
    return tuple(apps)


def out_dir_for(database_url: str) -> Path:
    """Where generated files live: next to a SQLite database file (a test's temp dir), else out/.
    One rule for every generated file (oauth key, mock identities, sync key, uploads)."""
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1]
        if path and path != ":memory:":
            return Path(path).resolve().parent
    return OUT_DIR


def _oauth_key(mode: str, out_dir: Path) -> str:
    """BOND_OAUTH_KEY, or in fake mode a key generated once and kept in oauth.key next to the database."""
    env = os.environ.get("BOND_OAUTH_KEY")
    if env:
        return env
    if mode != "fake":
        return ""
    path = out_dir / "oauth.key"
    if path.exists():
        return path.read_text().strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(32)
    path.write_text(key)
    return key


@dataclass(frozen=True)
class Settings:
    mode: str = "fake"
    database_url: str = "sqlite:///out/sdk_example.db"
    auth_secret: str = DEV_SECRET
    cors_origins: tuple[str, ...] = ("http://localhost:8078",)
    redirect_allowlist: tuple[str, ...] = ("http://localhost:8078",)
    native_redirects: tuple[str, ...] = ("sdkdemo://connections",)  # where a phone app's OAuth flow may return (exact match)
    oauth_key: str = ""
    tz: str = "UTC"
    # The default work day: what a person with nothing stored in their settings gets (they can override each value).
    start_of_day: str = "08:00"
    end_of_day: str = "17:00"
    lead_minutes: int = 60
    # Switching the notice sweep on over old tasks: a task due before this instant never sends a notice (None = off).
    grandfather_before: datetime | None = None
    # Direct sign-in (bond_signin). Real mode: public_base is https and names this API; sign-in providers are
    # off in real mode unless named (`google`, `microsoft`), and a provider named fake* is refused at startup.
    public_base: str = PUBLIC_BASE
    signin_providers: tuple[str, ...] = ()
    native_return_base: str = ""  # empty = `<public_base>/app/return`
    native_schemes: tuple[str, ...] = ()  # reverse-domain schemes a phone may return to (fallback); fake mode defaults to DEFAULT_SCHEME
    signin_prefix: str = "/auth"  # where the library mounts its routes; the app's own /auth/* routers keep /auth
    probe: bool = False  # SDK_EXAMPLE_PROBE=1: ask the provider daily whether the account still exists
    connections: bool = True  # SDK_EXAMPLE_CONNECTIONS=0: sign-in only, no connect routes (an app without mail)
    breakglass: bool = False  # the Firebase e-mail and password route (admin rows and the store reviewer)
    apple_app_ids: tuple[str, ...] = ()  # `<TEAMID>.<bundle id>` for the universal link file; empty = 404
    android_apps: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (package, sha256 fingerprints); empty = 404
    sync_url: str = ""  # PowerSync endpoint handed to clients by POST /sync/token; empty = sync off (fake mode defaults to a stand-in endpoint)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        mode = env("SDK_EXAMPLE_MODE", "fake")
        auth_secret = env("SDK_EXAMPLE_AUTH_SECRET", DEV_SECRET)
        if mode != "fake" and auth_secret == DEV_SECRET:
            raise RuntimeError("SDK_EXAMPLE_AUTH_SECRET must be set in real mode")
        fake = mode == "fake"  # real mode names every origin itself: no localhost defaults
        cors_origins = _split(env("SDK_EXAMPLE_CORS_ORIGINS", "http://localhost:8078" if fake else ""))
        if "*" in cors_origins:
            raise RuntimeError("SDK_EXAMPLE_CORS_ORIGINS must not contain '*' (credentials are on)")
        database_url = env("SDK_EXAMPLE_DATABASE_URL", "sqlite:///out/sdk_example.db")
        public_base = env("SDK_EXAMPLE_PUBLIC_BASE", "" if mode != "fake" else PUBLIC_BASE)
        if mode == "fake" and public_base.startswith("https://") and env("SDK_EXAMPLE_ALLOW_FAKE_PUBLIC") != "1":
            raise RuntimeError("fake mode on a public https address lets anyone sign in as anyone; "
                               "set SDK_EXAMPLE_ALLOW_FAKE_PUBLIC=1 only for a disposable demo host")
        if mode != "fake" and not public_base:
            raise RuntimeError("SDK_EXAMPLE_PUBLIC_BASE must be set in real mode")
        allowlist = _split(env("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "http://localhost:8078" if fake else ""))
        if not fake:
            if not allowlist:
                raise RuntimeError("SDK_EXAMPLE_REDIRECT_ALLOWLIST must be set in real mode (the web app's origin)")
            allowed = {_origin(a) for a in (*allowlist, public_base)}
            stray = [o for o in cors_origins if _origin(o) not in allowed]
            if stray:  # the sign-in Origin rule would answer 403 invalid_origin to this site on every sign-in POST
                raise RuntimeError(f"SDK_EXAMPLE_CORS_ORIGINS {stray} are not in the redirect allowlist or the public base")
        return cls(
            mode=mode,
            database_url=database_url,
            auth_secret=auth_secret,
            cors_origins=cors_origins,
            redirect_allowlist=allowlist,
            native_redirects=_split(env("SDK_EXAMPLE_NATIVE_REDIRECTS", "sdkdemo://connections" if fake else "")),
            oauth_key=_oauth_key(mode, out_dir_for(database_url)),
            tz=env("SDK_EXAMPLE_TZ", "UTC"),
            start_of_day=_hhmm("SDK_EXAMPLE_START_OF_DAY", env("SDK_EXAMPLE_START_OF_DAY", "08:00")),
            end_of_day=_hhmm("SDK_EXAMPLE_END_OF_DAY", env("SDK_EXAMPLE_END_OF_DAY", "17:00")),
            lead_minutes=_lead(env("SDK_EXAMPLE_LEAD_MINUTES", "60")),
            grandfather_before=_instant("SDK_EXAMPLE_GRANDFATHER_BEFORE", env("SDK_EXAMPLE_GRANDFATHER_BEFORE", "")),
            public_base=public_base.rstrip("/"),
            signin_providers=_split(env("SDK_EXAMPLE_SIGNIN_PROVIDERS", FAKE_PROVIDERS if mode == "fake" else "")),
            native_return_base=env("SDK_EXAMPLE_NATIVE_RETURN_BASE", ""),
            native_schemes=_split(env("SDK_EXAMPLE_NATIVE_SCHEMES", DEFAULT_SCHEME if fake else "")),  # no default in real mode
            signin_prefix="/" + env("SDK_EXAMPLE_SIGNIN_PREFIX", "/auth").strip("/"),
            probe=env("SDK_EXAMPLE_PROBE", "").lower() in ("1", "true", "yes", "on"),
            connections=env("SDK_EXAMPLE_CONNECTIONS", "1").lower() not in ("0", "false", "no", "off"),
            breakglass=env("SDK_EXAMPLE_BREAKGLASS", "").lower() in ("1", "true", "yes", "on"),
            apple_app_ids=_split(env("BOND_APPLE_APP_IDS", "")),
            android_apps=_android(env("BOND_ANDROID_APPS", "")),
            sync_url=env("SDK_EXAMPLE_SYNC_URL", FAKE_SYNC_URL if mode == "fake" else ""),
        )
