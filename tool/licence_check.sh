#!/usr/bin/env bash
# Checks the licences of resolved dependencies of the MIT modules (decision 2026-11-11-licence-mit, M5).
# Python: distributions installed in .venv (importlib.metadata). Dart: hosted/git packages listed in
# .dart_tool/package_config.json (first lines of each LICENSE file). Exit 1 on GPL/AGPL/LGPL or an
# unrecognised licence unless the package is in tool/allowlist_licences.txt. bash + python3 stdlib only.
# Env: PYTHON (default .venv/bin/python), DART_PACKAGE_CONFIG (default .dart_tool/package_config.json),
#      LICENCE_SKIP=python|dart skips one side.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
if [[ "${LICENCE_SKIP:-}" != "python" && ! -x "$PY" ]]; then
  echo "licence_check: $PY not found (run: uv sync --all-packages --all-extras)" >&2
  exit 2
fi
export LICENCE_PY="$PY" LICENCE_SKIP="${LICENCE_SKIP:-}"
export DART_PACKAGE_CONFIG="${DART_PACKAGE_CONFIG:-.dart_tool/package_config.json}"

python3 -I - <<'PYEOF'
import json, os, re, subprocess, sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path.cwd()


def norm(n):
    return re.sub(r"[-_.]+", "-", n).lower()


allow = {}
for line in (ROOT / "tool/allowlist_licences.txt").read_text().splitlines():
    name = line.split("#", 1)[0].strip()
    if name:
        allow[norm(name)] = line

# Distributions that only services/roof_measure needs (it is GPL-3.0-or-later and not covered by this check),
# plus this repo's own workspace members, read from the pyproject.toml files at run time (exact names).
PY_EXCLUDE = {"compas", "compas-cgal"}
for pp in sorted(ROOT.glob("libs/*/pyproject.toml")) + sorted(ROOT.glob("services/*/pyproject.toml")):
    m = re.search(r'^name\s*=\s*"([^"]+)"', pp.read_text(), re.M)
    if m:
        PY_EXCLUDE.add(norm(m.group(1)))

BAD = ("AGPL", "LGPL", "GPL")
RULES = [  # order matters: copyleft first
    ("AGPL", r"\bAGPL|AFFERO"),
    ("LGPL", r"\bLGPL|LESSER GENERAL"),
    ("GPL", r"\bGPL|GENERAL PUBLIC LICEN[SC]E"),
    ("MPL", r"\bMPL|MOZILLA PUBLIC"),
    ("Apache", r"APACHE"),
    ("MIT", r"\bMIT\b|MIT LICEN|PERMISSION IS HEREBY GRANTED"),
    ("BSD", r"\bBSD|REDISTRIBUTION AND USE IN SOURCE"),
    ("ISC", r"\bISC\b"),
    ("Zlib", r"\bZLIB"),
    ("PSF", r"\bPSF|PYTHON SOFTWARE FOUNDATION"),
    ("Unlicense", r"UNLICENSE|PUBLIC DOMAIN|\bCC0"),
]


def classify(text):
    t = text.upper()
    found = [name for name, rx in RULES if re.search(rx, t)]
    if not found:
        return "unknown"
    bad = [f for f in found if f in BAD]
    good = [f for f in found if f not in BAD]
    if bad and not (good and re.search(r"\bOR\b", t)):  # an SPDX "X OR Y" with a permissive option is fine
        return bad[0]
    return good[0] if good else bad[0]


results = []  # (kind, name, licence)

PY_PROBE = r'''
import importlib.metadata as m, json
out = []
for d in m.distributions():
    md = d.metadata
    cls = [c for c in (md.get_all("Classifier") or []) if c.startswith("License ::")]
    lic = (md.get("License-Expression") or "").strip()
    raw = (md.get("License") or "").strip()
    out.append([md.get("Name") or "", lic, " | ".join(cls), raw[:400]])
print(json.dumps(out))
'''


def py_side():
    r = subprocess.run([os.environ["LICENCE_PY"], "-I", "-c", PY_PROBE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("licence_check: cannot read the python environment:\n" + r.stderr)
    for name, expr, cls, raw in json.loads(r.stdout):
        n = norm(name)
        if not n or n in PY_EXCLUDE:
            continue
        text = expr or cls or raw
        results.append(("python", n, classify(text) if text else "unknown"))


def dart_side():
    cfg = Path(os.environ["DART_PACKAGE_CONFIG"])
    if not cfg.is_file():
        sys.exit(f"licence_check: {cfg} not found (run flutter pub get)")
    for p in json.loads(cfg.read_text())["packages"]:
        root = p["rootUri"]
        if "/hosted/" not in root and "/git/" not in root:
            continue  # workspace members and SDK packages
        d = Path(unquote(urlparse(root).path)) if root.startswith("file:") else (cfg.parent / root).resolve()
        files = sorted(d.glob("LICENSE*")) + sorted(d.glob("LICENCE*")) + sorted(d.glob("COPYING*"))
        lines = files[0].read_text(errors="replace").splitlines() if files else []
        head = [ln for ln in lines if ln.strip()]
        kind = classify(" ".join(head[:5])) if head else "unknown"
        if kind == "unknown" and head:
            kind = classify(" ".join(head[:40]))  # long preamble
        results.append(("dart", norm(p["name"]), kind))


skip = os.environ.get("LICENCE_SKIP", "")
for side, fn in (("python", py_side), ("dart", dart_side)):
    if skip == side:
        continue
    fn()
    if not any(k == side for k, _, _ in results):
        sys.exit(f"licence_check: the {side} side found zero packages; refusing to pass")

fail = [(k, n, l) for k, n, l in results if (l in BAD or l == "unknown") and n not in allow]
for kind in ("python", "dart"):
    c = Counter(l for k, _, l in results if k == kind)
    if c:
        print(f"{kind}: {sum(c.values())} packages: " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
allowed_bad = [(k, n, l) for k, n, l in results if (l in BAD or l == "unknown") and n in allow]
if allowed_bad:
    print("allowlisted: " + ", ".join(f"{n}({l})" for _, n, l in allowed_bad))
if fail:
    print("FAIL: GPL-family or unrecognised licence (fix the dependency or add it to tool/allowlist_licences.txt with a reason):")
    for kind, name, lic in fail:
        print(f"  {kind} {name}: {lic}")
    sys.exit(1)
print("licence check ok")
PYEOF
