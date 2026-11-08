"""Debug picture of a roof model: facets by kind, edges by type, whole-foot length labels.

WHY: the Dart side draws the real diagrams; this PNG lets the service be judged without it.
Colours are the contract palette (docs/contracts/roof_model.md section 4).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon

PALETTE = {"eave": "#2E7D32", "ridge": "#8BC34A", "hip": "#5E35B1", "valley": "#E53935", "rake": "#FBC02D",
           "step_flashing": "#8D6E63", "wall_flashing": "#1E88E5", "parapet": "#FB8C00",
           "transition": "#D81B60", "unspecified": "#26A69A"}
DASHED = {"step_flashing", "wall_flashing"}
FILL = {"flat": "#E3F2FD", "sloped": "#FFF8E1"}


def slug(text: str) -> str:
    """File-name slug of an address or label."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "model"


def ft_in(v: float) -> str:
    total = round(v * 12)
    return f"{total // 12}ft {total % 12}in"


def render_png(model: dict[str, Any], path: str | Path) -> Path:
    """Write the debug PNG for ``model`` and return its path."""
    fig, ax = plt.subplots(figsize=(15, 8), dpi=110)
    xs = [p[0] for f in model["facets"] for p in f["polygon"]]
    ys = [p[1] for f in model["facets"] for p in f["polygon"]]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    for f in model["facets"]:
        ax.add_patch(MplPolygon(f["polygon"], closed=True, facecolor=FILL[f["kind"]], edgecolor="#9E9E9E",
                                linewidth=0.6, alpha=0.95, zorder=1))
        cx = sum(p[0] for p in f["polygon"]) / len(f["polygon"])
        cy = sum(p[1] for p in f["polygon"]) / len(f["polygon"])
        label = "Flat" if f["kind"] == "flat" else f"{f['pitch_rise']:.1f}/12"
        if f["plan_area_sqft"] > 0.004 * span * span:
            ax.text(cx, cy, f"{label}\n{f['area_sqft']:.0f} sf", ha="center", va="center", fontsize=7, color="#37474F",
                    zorder=2)
    for e in model["edges"]:
        (x1, y1), (x2, y2) = e["points"]
        ax.plot([x1, x2], [y1, y2], color=PALETTE[e["type"]], linewidth=2.4,
                linestyle="--" if e["type"] in DASHED else "-", solid_capstyle="butt", zorder=3)
        if e["length_ft"] > 0.035 * span:
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            ang = ang + 180 if ang > 90 or ang < -90 else ang
            ax.text((x1 + x2) / 2, (y1 + y2) / 2, f"{e['length_ft']:.0f}", fontsize=6.5, rotation=ang, ha="center",
                    va="center", color="#212121", zorder=4,
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.4, "alpha": 0.75})
    t = model["totals"]
    handles = [Line2D([0], [0], color=PALETTE[k], lw=3, ls="--" if k in DASHED else "-",
                      label=f"{k.replace('_', ' ')}  {ft_in(v)}") for k, v in t["lengths_ft"].items()]
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False,
              title="Lengths", title_fontsize=9)
    addr = model["address"].get("formatted") or model["address"].get("line1", "")
    ax.set_title(f"{addr}   |   {model['source']['method']}   |   total {t['total_area_sqft']:.0f} sf "
                 f"({t['squares']:.1f} sq), pitched {t['pitched_area_sqft']:.0f}, flat {t['flat_area_sqft']:.0f}, "
                 f"predominant {t['predominant_pitch_rise']:.1f}/12   |   confidence {model['confidence']['overall']}",
                 fontsize=9)
    ax.set_aspect("equal")
    ax.autoscale()
    ax.margins(0.03)
    ax.grid(color="#EEEEEE", linewidth=0.5)
    ax.set_xlabel("east (ft)")
    ax.set_ylabel("north (ft)")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out
