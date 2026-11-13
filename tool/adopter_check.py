#!/usr/bin/env python3
"""Run an adopting app's own regression battery against THIS bond-factory working tree.

Usage: python3 tool/adopter_check.py --app <checkout> --bond <bond-factory> [--config FILE] [--suite NAME] [--keep] [--list]
Reads <app>/.bond-adopter.toml (docs/sdk/adopter-check.md). The app is copied to a temp dir
(tracked + untracked-not-ignored files when it is a git checkout) and never written to.
Exit: 0 all PASS, 1 any FAIL/TIMEOUT/SKIPPED, 2 validation error.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    print("adopter-check needs Python 3.11+; run `make setup-py` or use a newer python3")
    sys.exit(2)

import argparse
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adopter_config import Config, ConfigError, Project, Suite, closure, load  # noqa: E402

SKIP_DIRS = {".git", ".venv", ".dart_tool", "build", "node_modules"}


def git(path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}  # read-only: never refresh the app's index
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, env=env)


def is_git(path: Path) -> bool:
    return git(path, "rev-parse", "--is-inside-work-tree").stdout.strip() == b"true"


def revision(path: Path) -> str:
    if not is_git(path):
        return "no git"
    sha = git(path, "rev-parse", "--short", "HEAD").stdout.decode().strip() or "unborn"
    dirty = git(path, "status", "--porcelain", "--", ".").stdout.strip()
    return sha + (" (dirty)" if dirty else "")


def file_list(app: Path, extra: list[str], cfg: Config) -> list[str]:
    if is_git(app):
        out = git(app, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
        names = [os.fsdecode(n) for n in out.split(b"\0") if n]
    else:
        # Skipped: SKIP_DIRS at the app root, and .dart_tool/build inside each project dir.
        skip = set(SKIP_DIRS) | {f"{p.dir}/{n}".lstrip("/") for p in cfg.projects for n in (".dart_tool", "build")}
        names = []
        for root, dirs, files in os.walk(app):
            here = os.path.relpath(root, app)
            dirs[:] = [d for d in dirs if os.path.normpath(os.path.join(here, d)) not in skip]
            names += [os.path.relpath(os.path.join(root, f), app) for f in files]
    for e in extra:
        if e not in names and (app / e).exists():
            names.append(e)
    return sorted(set(names))


def copy_app(app: Path, names: list[str], dest: Path) -> None:
    dest.mkdir(parents=True)
    for n in names:
        src = app / n
        if not (src.is_symlink() or src.is_file()):
            continue  # listed by git but deleted, or a submodule directory
        out = dest / n
        if not out.parent.resolve().is_relative_to(dest.resolve()):
            continue  # its parent is a symlink that leads out of the copy
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out, follow_symlinks=False)


def fill(cmd: str, bond: Path, copy: Path, lib: str = "") -> str:
    q = shlex.quote  # a path with spaces or quotes stays one shell word
    return cmd.replace("{bond}", q(str(bond))).replace("{copy}", q(str(copy))).replace("{lib}", q(lib) if lib else "")


def run_cmd(cmd: str, cwd: Path, env: dict, log: Path, timeout: int) -> str:
    """Run via /bin/sh -c, output to `log`. Returns PASS, FAIL or TIMEOUT."""
    cwd.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as fh:
        fh.write(f"$ {cmd}\n".encode())
        fh.flush()
        p = subprocess.Popen(["/bin/sh", "-c", cmd], cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                             start_new_session=True)
        try:
            return "PASS" if p.wait(timeout=timeout) == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        finally:  # also reaps background processes the command left behind
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()


def tail(log: Path, n: int = 30) -> None:
    lines = log.read_text(errors="replace").splitlines()[-n:] if log.exists() else []
    for line in lines:
        print(f"    | {line}")


def inside(d: str, parent: str) -> bool:
    return parent == "" or d == parent or d.startswith(parent + "/")


def point_flutter(p: Project, copy: Path, bond: Path) -> None:
    lines = ["dependency_overrides:"]
    for n in closure(bond, p.names):
        target = str(bond / "packages" / n).replace("\\", "\\\\").replace('"', '\\"')
        lines += [f"  {n}:", f'    path: "{target}"']
    (copy / p.dir / "pubspec_overrides.yaml").write_text("\n".join(lines) + "\n")


def prepare(cfg: Config, bond: Path, copy: Path, env: dict, logs: Path):
    """Run setup and overlay per project. Returns (failed rows, dirs of the failed projects)."""
    rows, failed = [], []
    for p in cfg.projects:
        label = f"setup:{p.dir or '.'}"
        log = logs / (label.replace("/", "_").replace(":", "-") + ".log")
        t0 = time.time()
        if p.kind == "flutter":
            point_flutter(p, copy, bond)
        steps = [fill(c, bond, copy) for c in p.setup]
        steps += [fill(p.overlay, bond, copy, str(bond / "libs" / lib)) for lib in p.names] if p.kind == "python" else []
        for cmd in steps:
            res = run_cmd(cmd, copy / p.dir, env, log, 1800)
            if res != "PASS":
                rows.append((label, res, time.time() - t0, log))
                tail(log)
                failed.append(p.dir)
                break
    return rows, failed


def run_battery(cfg: Config, suites: list[Suite], bond: Path, copy: Path) -> list[tuple[str, str, float, Path]]:
    logs = copy / ".adopter-logs"
    logs.mkdir()
    base = {**os.environ, "GIT_CEILING_DIRECTORIES": str(copy.parent)}
    rows, failed = prepare(cfg, bond, copy, base, logs)
    for s in suites:
        log = logs / f"{s.name}.log"
        if any(inside(s.dir, f) for f in failed):
            rows.append((s.name, "SKIPPED", 0.0, log))
            continue
        t0 = time.time()
        res = run_cmd(fill(s.run, bond, copy), copy / s.dir, {**base, **s.env}, log, s.timeout)
        rows.append((s.name, res, time.time() - t0, log))
        if res != "PASS":
            tail(log)
    return rows


def print_plan(cfg: Config, suites: list[Suite]) -> None:
    print(f"copy extra: {cfg.extra or '-'}")
    for p in cfg.projects:
        print(f"{p.kind} {p.dir or '.'}: setup={p.setup} {'overlay=' + p.overlay if p.overlay else ''} {p.names}")
    for s in suites:
        print(f"suite {s.name}: dir={s.dir or '.'} timeout={s.timeout}s env={s.env} run={s.run}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", required=True, help="the adopting app's checkout")
    ap.add_argument("--bond", required=True, help="this bond-factory checkout")
    ap.add_argument("--config", help="read the adopter file from here instead of <app>/.bond-adopter.toml")
    ap.add_argument("--suite", help="run only this suite")
    ap.add_argument("--keep", action="store_true", help="keep the temp copy and print its path")
    ap.add_argument("--list", action="store_true", help="print the parsed plan and run nothing")
    a = ap.parse_args()
    app, bond = Path(a.app).expanduser().resolve(), Path(a.bond).expanduser().resolve()
    config = Path(a.config).expanduser().resolve() if a.config else None
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(143))  # so `finally` removes the copy
    try:
        if not app.is_dir():
            raise ConfigError(f"app {app} is not a directory")
        cfg = load(app, bond, config)
        suites = [s for s in cfg.suites if a.suite in (None, s.name)]
        if not suites:
            raise ConfigError(f"no suite named {a.suite!r}")
        names = file_list(app, cfg.extra, cfg)
        for p in cfg.projects:
            if p.kind == "flutter" and (f"{p.dir}/pubspec_overrides.yaml" if p.dir else "pubspec_overrides.yaml") in names:
                raise ConfigError(f"{p.dir or '.'}/pubspec_overrides.yaml would be copied; it must not be tracked")
    except ConfigError as e:
        print(f"adopter-check: {e}", file=sys.stderr)
        return 2
    if a.list:
        print_plan(cfg, suites)
        return 0
    work = Path(tempfile.mkdtemp(prefix="adopter-"))
    copy = work / "app"
    try:
        copy_app(app, names, copy)
        bad = next((d for d in [p.dir for p in cfg.projects] + [s.dir for s in suites]
                    if not (copy / d).resolve().is_relative_to(copy.resolve())), None)
        if bad is not None:
            print(f"adopter-check: dir {bad!r} leads outside the copy (a symlink?)", file=sys.stderr)
            return 2
        rows = run_battery(cfg, suites, bond, copy)
        print(f"\n{'suite':<24}{'result':<9}{'secs':>7}  log")
        for name, res, secs, log in rows:
            print(f"{name:<24}{res:<9}{secs:>7.1f}  {log}")
        print(f"\nbond {revision(bond)}, app {revision(app)}: "
              f"{sum(r[1] == 'PASS' for r in rows)}/{len(rows)} PASS")
        if a.keep:
            print(f"kept copy: {copy}")
        return 0 if rows and all(r[1] == "PASS" for r in rows) else 1
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
