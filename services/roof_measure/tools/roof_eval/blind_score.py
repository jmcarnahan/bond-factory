"""roof-blind-score: grades.tsv + the withheld key -> A/B/C counts per candidate with Wilson 95% intervals.

grades.tsv, tab separated, either long (``house grader candidate grade``, candidate X|Y|Z) or wide
(``house grader X Y Z``); grade A, B or C. Counts are over graded (house, grader) cells, overall and per pooled stratum;
the interval treats cells as independent (two graders on one house are not, say so when quoting it). Agreement is the
share of identical grades between each pair of graders on the cells both graded.
"""

from __future__ import annotations

import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .stats import wilson

GRADES = ("A", "B", "C", "R")  # R = no drawing: counted separately, outside the A/B/C shares
LETTERS = ("X", "Y", "Z")


def read_grades(path: Path) -> list[tuple[str, str, str, str]]:
    """(house, grader, letter, grade) rows. Layout from the header when there is one (a ``candidate`` column = long, else
    wide with the candidate letters X, Y, Z among the columns; a column whose name contains ``note`` or ``comment``, e.g.
    ``X_note``, is a note and is ignored; any other name is an error),
    without a header from the third column (a letter X/Y/Z with 4 or 5 columns = long, else wide in the order X, Y, Z).
    Grades A, B, C or R (no drawing); an empty cell is skipped. Unknown letters or grades are errors."""
    rows = [[c.strip() for c in r] for r in csv.reader(path.read_text().splitlines(), delimiter="\t") if r and not r[0].startswith("#")]
    head = None
    if rows and rows[0][0].lower() in ("house", "h"):
        head, rows = [c.upper() for c in rows[0]], rows[1:]
        for h in head[2:]:
            if h not in LETTERS and h != "CANDIDATE" and h != "GRADE" and "NOTE" not in h and "COMMENT" not in h:
                raise SystemExit(f"unknown candidate letter {h!r} in the header (use X, Y, Z; note columns contain 'note')")
    out = []
    for r in rows:
        if head is not None:
            long = "CANDIDATE" in head
            cells = [(r[2], r[3])] if long and len(r) > 3 else [(h, r[k]) for k, h in enumerate(head) if k >= 2 and k < len(r) and h in LETTERS]
        elif len(r) in (4, 5) and r[2].upper() in LETTERS and (len(r[3]) <= 1):
            cells = [(r[2], r[3])]
        else:
            cells = list(zip("XYZ", r[2:5], strict=False))
        for letter, g in cells:
            letter, g = letter.upper(), g.upper()
            if letter not in LETTERS:
                raise SystemExit(f"unknown candidate letter {letter!r} for house {r[0]} (use X, Y, Z)")
            if g and g not in GRADES:
                raise SystemExit(f"bad grade {g!r} for house {r[0]}")
            if g:
                out.append((r[0], r[1], letter, g))
    return out


def _share(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "share": k / n if n else None, "lo95": lo, "hi95": hi}


def score(grades: list[tuple[str, str, str, str]], key: dict[str, Any], graders: list[str] | None = None) -> dict[str, Any]:
    """Per candidate label: counts and A / C shares with Wilson intervals, overall, per stratum and per grader."""
    cells: dict[tuple[str, str, str], str] = {}
    for h, who, letter, g in grades:
        if graders and who not in graders:
            continue
        cells[(h, who, letter)] = g
    counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    unknown = set()
    for (h, who, letter), g in cells.items():
        kh = key["houses"].get(h)
        if kh is None:
            unknown.add(h)
            continue
        if letter not in kh:
            raise SystemExit(f"house {h}: grade for candidate {letter}, but the key has no such candidate")
        cand = kh[letter]
        groups = ["overall", f"stratum:{kh['stratum']}", f"grader:{who}"]
        if (kh.get("ok") or {}).get(letter):
            groups.append("labelled_ok")  # plan gate 4: the C-share among results the engine labelled ok
        for grp in groups:
            counts[cand][grp][g] += 1
    res: dict[str, Any] = {"unknown_houses": sorted(unknown), "candidates": {}}
    for cand, grp in sorted(counts.items()):
        res["candidates"][cand] = {}
        for name, c in sorted(grp.items()):
            n = c["A"] + c["B"] + c["C"]  # shares are over the graded drawings; R is reported beside them
            res["candidates"][cand][name] = {"A": c["A"], "B": c["B"], "C": c["C"], "R": c["R"], "n": n, "n_with_R": n + c["R"],
                                             "A_share": _share(c["A"], n), "C_share": _share(c["C"], n)}
    agree = {}
    who = sorted({w for _, w, _ in cells})
    for a, b in itertools.combinations(who, 2):
        common = [(h, letter) for (h, w, letter) in cells if w == a and (h, b, letter) in cells]
        same = sum(1 for h, letter in common if cells[(h, a, letter)] == cells[(h, b, letter)])
        agree[f"{a}~{b}"] = {"cells": len(common), "same": same, "agreement": same / len(common) if common else None}
    res["agreement"] = agree
    return res


def _fmt(x: dict[str, Any]) -> str:
    return "-" if x["share"] is None else f"{100 * x['share']:.0f}% [{100 * x['lo95']:.0f}, {100 * x['hi95']:.0f}]"


def render(res: dict[str, Any]) -> str:
    lines = ["# blind scores", "", "| candidate | group | n (A+B+C) | A | B | C | R | A share [95%] | C share [95%] |", "|---|---|---|---|---|---|---|---|---|"]
    for cand, grp in res["candidates"].items():
        for name, s in grp.items():
            a, c = s["A_share"], s["C_share"]
            lines.append(f"| {cand} | {name} | {s['n']} | {s['A']} | {s['B']} | {s['C']} | {s['R']} | {_fmt(a)} | {_fmt(c)} |")
    lines += ["", "grader agreement (identical grades): " + json.dumps(res["agreement"]),
              "Wilson intervals treat graded (house, grader) cells as independent; two graders on one house are not."]
    return "\n".join(lines) + "\n"
