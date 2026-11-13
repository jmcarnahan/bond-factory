"""Parse and validate an adopter's .bond-adopter.toml (format version 1; docs/sdk/adopter-check.md)."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class ConfigError(Exception):
    """A validation error; the message is one line."""


@dataclass
class Project:
    kind: str  # "python" or "flutter"
    dir: str  # normalised, "" = app root
    setup: list[str] = field(default_factory=list)
    overlay: str = ""
    names: list[str] = field(default_factory=list)  # libs or packages


@dataclass
class Suite:
    name: str
    dir: str
    run: str
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 1800


@dataclass
class Config:
    extra: list[str]
    projects: list[Project]
    suites: list[Suite]


def rel_dir(value: object, what: str) -> str:
    """A path that stays inside the app: relative, no `..`. Returns it normalised ('' = root)."""
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{what} must be a non-empty string")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ConfigError(f"{what} {value!r} must be relative and stay inside the app")
    s = str(p)
    return "" if s == "." else s


def _strs(table: dict, key: str, what: str) -> list[str]:
    v = table.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ConfigError(f"{what}.{key} must be a list of strings")
    return v


def _project(kind: str, t: dict, app: Path, bond: Path) -> Project:
    what = f"[[{kind}]]"
    d = rel_dir(t.get("dir", "."), f"{what} dir")
    if not (app / d).is_dir():
        raise ConfigError(f"{what} dir {d or '.'!r} is not a directory in the app")
    key, root = ("libs", "libs") if kind == "python" else ("packages", "packages")
    names = _strs(t, key, what)
    for n in names:
        if not NAME.match(n) or not (bond / root / n).is_dir():
            raise ConfigError(f"{what} {key[:-1]} {n!r} does not exist under {bond / root}")
    overlay = t.get("overlay", "")
    if kind == "python" and names and not (isinstance(overlay, str) and overlay):
        raise ConfigError(f"{what} names libs but has no overlay command")
    return Project(kind, d, _strs(t, "setup", what), overlay if kind == "python" else "", names)


def _suite(t: dict, app: Path) -> Suite:
    name = t.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        raise ConfigError("[[suite]] name must match [A-Za-z0-9_][A-Za-z0-9_.-]*")
    d = rel_dir(t.get("dir", "."), f"suite {name!r} dir")
    if not (app / d).is_dir():
        raise ConfigError(f"suite {name!r} dir {d or '.'!r} is not a directory in the app")
    run = t.get("run")
    if not isinstance(run, str) or not run.strip():
        raise ConfigError(f"suite {name!r} needs a run command")
    env = t.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ConfigError(f"suite {name!r} env must be a table of strings")
    timeout = t.get("timeout", 1800)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ConfigError(f"suite {name!r} timeout must be a positive integer (seconds)")
    return Suite(name, d, run, dict(env), timeout)


SIBLING = re.compile(r"path:\s*\.\./([A-Za-z0-9_]+)")


def closure(bond: Path, names: list[str]) -> list[str]:
    """The named packages plus every bond sibling they reach through `path: ../<sibling>` (line scan, no YAML lib)."""
    out, todo = list(names), list(names)
    while todo:
        spec = bond / "packages" / todo.pop() / "pubspec.yaml"
        if not spec.is_file():
            continue
        for sib in SIBLING.findall(spec.read_text(encoding="utf-8")):
            if sib not in out and (bond / "packages" / sib).is_dir():
                out.append(sib)
                todo.append(sib)
    return out


def load(app: Path, bond: Path, config: Path | None = None) -> Config:
    path = config or app / ".bond-adopter.toml"
    if not path.is_file():
        raise ConfigError(f"{path} not found (the app owns this file; see docs/sdk/adopter-check.md)")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ConfigError(f"{path.name} does not parse: {e}") from None
    if data.get("version") != 1:
        raise ConfigError(f"{path.name} version must be 1, got {data.get('version')!r}")
    extra = [rel_dir(x, "[copy].extra entry") for x in _strs(data.get("copy", {}), "extra", "[copy]")]
    projects = [_project("python", t, app, bond) for t in data.get("python", [])]
    projects += [_project("flutter", t, app, bond) for t in data.get("flutter", [])]
    suites = [_suite(t, app) for t in data.get("suite", [])]
    if not suites:
        raise ConfigError(f"{path.name} defines no [[suite]]")
    names = [s.name for s in suites]
    if len(set(names)) != len(names):
        raise ConfigError("suite names must be unique")
    return Config(extra, projects, suites)
