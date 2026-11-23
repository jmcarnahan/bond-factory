"""roof-blind: a stratified draw of houses and one anonymous PNG per house (candidates X / Y / Z, drawn by one renderer).

``key.json`` (house label -> opaque id, stratum, which candidate sits under X / Y / Z) is written to a path the grader is
not given and never inside the image directory. Candidates are directories of ``<id>.json`` results: a run's
``results/`` folder, ``baseline:NAME`` (under the data root), or any folder.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from . import data, render


def stratified_draw(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """n rows, round-robin over the pooled strata (pitched, flat+mixed, complex), each stratum shuffled by ``seed``."""
    rng = random.Random(seed)
    pools: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        pools.setdefault(data.pooled_stratum(r), []).append(r)
    for k in sorted(pools):
        rng.shuffle(pools[k])
    out: list[dict[str, Any]] = []
    while len(out) < min(n, len(rows)):
        for k in sorted(pools):
            if pools[k] and len(out) < n:
                out.append(pools[k].pop())
    rng.shuffle(out)
    return out


def resolve_candidate(spec: str, root: Path) -> tuple[str, Path]:
    """``label=path`` or ``label=baseline:NAME``; the label is only for the key, never drawn."""
    label, _, p = spec.partition("=")
    if not p:
        raise SystemExit(f"candidate {spec!r}: expected label=<dir of results | baseline:NAME>")
    d = root / "baselines" / p.split(":", 1)[1] / "results" if p.startswith("baseline:") else Path(p)
    if not d.is_dir():
        raise SystemExit(f"candidate {label}: {d} is not a directory")
    return label, d


def load_candidate(d: Path, hid: str) -> dict[str, Any] | None:
    return data.load_json(d / f"{hid}.json") or data.load_json(d / hid / "result.json")


def make(root: Path, rows: list[dict[str, Any]], cands: list[str], n: int, seed: int, out_dir: Path, key_path: Path) -> dict[str, Any]:
    """Draw, render and write the key. Returns the key."""
    if len(cands) < 2 or len(cands) > 3:
        raise SystemExit("roof-blind needs 2 or 3 candidates (--cand label=dir)")
    if out_dir.resolve() in key_path.resolve().parents or key_path.resolve().parent == out_dir.resolve():
        raise SystemExit("the key must be written outside the image directory")
    cs = [resolve_candidate(c, root) for c in cands]
    rng = random.Random(seed ^ 0x5EED)
    picked = stratified_draw(rows, n, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    key: dict[str, Any] = {"seed": seed, "candidates": [c[0] for c in cs], "houses": {}}
    for i, row in enumerate(picked, 1):
        lab = f"H{i:03d}"
        hid = row["id"]
        hd = data.house_dir(root, hid)
        perm = list(range(len(cs)))
        rng.shuffle(perm)
        panels = [(letter, load_candidate(cs[j][1], hid)) for letter, j in zip("XYZ", perm, strict=False)]
        good = {letter: bool(res and res.get("facets") and ((res.get("diagnostics") or {}).get("quality") or {}).get("verdict", "ok") == "ok")
                for letter, res in panels}
        render.render_sheet(out_dir / f"{lab}.png", lab, data.reference_points(hd), data.House(hid, hd, row).wide(),
                            data.parse_polygon(data.load_json(hd / "footprint.json")), hd / "orthophoto.png", panels)
        key["houses"][lab] = {"id": hid, "stratum": data.pooled_stratum(row), "ok": good,
                              **{letter: cs[j][0] for letter, j in zip("XYZ", perm, strict=False)}}
    (out_dir / "manifest.json").write_text(json.dumps({"houses": sorted(key["houses"]), "letters": list("XYZ"[: len(cs)])}))
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, indent=1))
    return key
