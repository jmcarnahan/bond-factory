"""Find printed text in a PDF and turn it into a signature box.

Placements are fractions of the visible page (the CropBox when there is one, else the MediaBox), the same box
``stamp`` uses.
Limits (v1): pages with a /Rotate other than 0 are skipped. The right edge of the matched text is an estimate:
the run's width is measured with Helvetica metrics at the run's font size, not the font the PDF embeds.
"""

import io
import re
from dataclasses import dataclass

from bond_esign.errors import INVALID_PDF, EsignError
from bond_esign.pdf_read import is_rotated, visible_box
from bond_esign.types import AnchorRule, Placement

_LINE_TOLERANCE = 2.0  # points: runs whose baselines differ by less share a line
_GAP_EM = 0.15  # a horizontal gap wider than this many em, with no space either side, counts as a space


@dataclass
class _Run:
    text: str
    x: float
    y: float
    size: float


def _width(text: str, size: float) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    try:
        return stringWidth(text, "Helvetica", size)
    except Exception:  # noqa: BLE001  characters Helvetica cannot measure: fall back to a flat estimate
        return 0.5 * size * len(text)


def _collect_runs(page) -> list[_Run]:
    runs: list[_Run] = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        scale = abs(tm[0] * cm[0]) or abs(tm[3] * cm[3]) or 1.0
        size = (font_size or 10.0) * (scale if scale > 0.01 else 1.0)
        runs.append(_Run(text, float(x), float(y), float(size)))

    page.extract_text(visitor_text=visitor)
    return runs


def _group_lines(runs: list[_Run]) -> list[list[_Run]]:
    lines: list[list[_Run]] = []
    for run in sorted(runs, key=lambda r: -r.y):
        if lines and abs(lines[-1][0].y - run.y) <= _LINE_TOLERANCE:
            lines[-1].append(run)
        else:
            lines.append([run])
    for line in lines:
        line.sort(key=lambda r: r.x)
    return lines


def _flatten(line: list[_Run], fold: bool):
    """Joined, whitespace-collapsed line text plus, per character, (run index, offset in run)."""
    chars: list[str] = []
    origin: list[tuple[int, int]] = []
    prev_end = None
    for ri, run in enumerate(line):
        gap = prev_end is not None and run.x - prev_end > _GAP_EM * run.size
        if gap and chars and chars[-1] != " " and not run.text[0].isspace():
            chars.append(" ")
            origin.append((ri, 0))
        for oi, ch in enumerate(run.text):
            if ch.isspace():
                if chars and chars[-1] != " ":
                    chars.append(" ")
                    origin.append((ri, oi))
                continue
            chars.append(ch.lower() if fold else ch)
            origin.append((ri, oi))
        prev_end = run.x + _width(run.text, run.size)
    return "".join(chars), origin


def _needle(text: str, case_sensitive: bool) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip())
    return collapsed if case_sensitive else collapsed.lower()


def _matches(runs: list[_Run], needle: str, case_sensitive: bool):
    """Yield (right_edge_x, baseline_y) for every match on a page in reading order."""
    for line in _group_lines(runs):
        flat, origin = _flatten(line, not case_sensitive)
        start = flat.find(needle)
        while start != -1:
            end = start + len(needle) - 1
            ri, oi = origin[end]
            run = line[ri]
            right = run.x + _width(run.text[: oi + 1], run.size)
            yield right, sum(r.y for r in line) / len(line)
            start = flat.find(needle, end + 1)


def find_anchor(pdf: bytes, rule: AnchorRule) -> Placement | None:
    """Locate ``rule.text`` and return the box ``rule`` describes, or None when there is no such match.

    ``occurrence`` counts matches over all pages in reading order (page, top to bottom, left to right);
    -1 is the last. Out of range gives None.
    """
    from pypdf import PdfReader

    needle = _needle(rule.text, rule.case_sensitive)
    if not needle:
        return None
    try:
        reader = PdfReader(io.BytesIO(pdf))
        pages = list(reader.pages)
    except Exception as exc:
        raise EsignError(INVALID_PDF, "This file is not a readable PDF.") from exc

    found: list[Placement] = []
    for number, page in enumerate(pages, start=1):
        if is_rotated(page):
            continue
        x0, y0, width, height = visible_box(page)
        if width <= 0 or height <= 0:
            continue
        try:
            runs = _collect_runs(page)
        except Exception:  # noqa: BLE001, S112  a page pypdf cannot read has no findable text
            continue
        for right, baseline in _matches(runs, needle, rule.case_sensitive):
            x = (right - x0) / width + rule.dx
            y = 1 - (baseline - y0) / height + rule.dy
            x = min(max(x, 0.0), max(0.0, 1 - rule.w))
            y = min(max(y, 0.0), max(0.0, 1 - rule.h))
            found.append(Placement(number, round(x, 5), round(y, 5), rule.w, rule.h))
    try:
        return found[rule.occurrence]
    except IndexError:
        return None
