"""Aggregation of per-house records into overall and per-stratum numbers, and their markdown tables."""

from __future__ import annotations

from collections import Counter
from typing import Any

from . import data, m_truth, stats
from .gates import metric

MEDIAN_KEYS = ("fit_all", "fit_covered", "coverage", "facets", "facets_lt_30sqft", "edges_lt_3ft", "axis_share_7deg",
               "false_level_change_share", "overlap_sqft", "tiling_gap_sqft")
GROUP_KEYS = ("split", "roof_class", "region", "pooled", "density_band", "pitch_band", "parcel_match")


def _med(recs, key):
    return stats.median([metric(r, key) for r in recs])


def aggregate(recs: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts, rates and medians of one group of per-house records."""
    n = len(recs)
    ok = [r for r in recs if r.get("automation_ok")]
    have = [r for r in recs if r.get("automation")]
    t1 = [metric(r, "truth.T1.squares.err_pct") for r in recs]
    out: dict[str, Any] = {
        "n": n, "n_result": len(have), "n_ok": len(ok),
        "automation_rate": len(ok) / n if n else None,
        "verdicts": dict(Counter(str(r.get("verdict")) for r in have)),
        "parcel_match": dict(Counter(str(r["row"].get("parcel_match")) for r in recs)),
        "failures": dict(Counter(r["engine"]["status"] for r in recs if r["engine"]["status"] != "ok")),
        "median": {k: _med(have, k) for k in MEDIAN_KEYS},
        "fit_all_p10": stats.percentile([metric(r, "fit_all") for r in have], 10),
        "overlap_houses": sum(1 for r in have if (metric(r, "overlap_sqft") or 0) > 1.0),
        "T2_label_disagree": sum(1 for r in recs if (r.get("t2_labels") or {}).get("disagree")),
        "T2_two_label_houses": sum(1 for r in recs if r.get("t2_labels")),
        "priced_inconsistent_houses": sum(1 for r in have if metric(r, "priced_inconsistent")),
        "priced_from_totals_houses": sum(1 for r in have if "totals" in ((metric(r, "priced.src") or {}).values())),
        "runtime_median_s": stats.median([r.get("runtime_s") for r in recs]),
        "runtime_p90_s": stats.percentile([r.get("runtime_s") for r in recs], 90),
        "T1_squares_abs_err_pct_median": stats.median([abs(x) for x in t1 if x is not None]),
        "T1_n": sum(1 for x in t1 if x is not None),
        "T2_facet_iou_mean": stats.mean([metric(r, "truth.T2.facet_iou.mean_iou") for r in recs]),
        "T2_n": sum(1 for r in recs if metric(r, "truth.T2.facet_iou.mean_iou") is not None),
        "T2_flat_pitched_agreement": stats.mean([metric(r, "truth.T2.flat_pitched_agreement") for r in recs]),
        "price_abs_pct_median_T1": stats.median([abs(x) for x in (metric(r, "truth.T1.price.total.pct") for r in recs) if x is not None]),
        "price_abs_pct_median_T2": stats.median([abs(x) for x in (metric(r, "truth.T2.price.total.pct") for r in recs) if x is not None]),
    }
    return out


def aggregate_all(recs: list[dict[str, Any]]) -> dict[str, Any]:
    """Overall, per stratum (each grouping key), and the T3 aggregate."""
    canaries = [r for r in recs if data.is_canary(r["row"])]
    recs = [r for r in recs if not data.is_canary(r["row"])] or recs  # canaries are never evidence
    by: dict[str, dict[str, Any]] = {}
    for k in GROUP_KEYS:
        vals = sorted({str(r["row"].get(k)) for r in recs})
        if len(vals) > 1 or (vals and vals != ["None"]):
            by[k] = {v: aggregate([r for r in recs if str(r["row"].get(k)) == v]) for v in vals}
    return {"overall": aggregate(recs), "by": by, "t3": m_truth.t3_aggregate(recs), "t3_drawn": m_truth.t3_aggregate(recs, "ratio_drawn"),
            "canaries": [{"id": r["id"], "verdict": r.get("verdict"), "status": r.get("status"),
                          **{k: (r.get("m") or {}).get(k) for k in ("fit_all", "fit_covered", "coverage", "facets", "area_sqft")},
                          "T2_iou": metric(r, "truth.T2.facet_iou.mean_iou")} for r in canaries]}


def _f(x, nd=3):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def _row(label: str, a: dict[str, Any]) -> str:
    md = a["median"]
    return (f"| {label} | {a['n']} | {_f(a['automation_rate'], 2)} | {_f(md['fit_all'], 2)} | {_f(md['fit_covered'], 2)} | "
            f"{_f(md['coverage'], 2)} | {_f(md['facets'], 1)} | {_f(md['facets_lt_30sqft'], 1)} | {_f(md['edges_lt_3ft'], 1)} | "
            f"{_f(md['axis_share_7deg'], 2)} | {_f(md['false_level_change_share'], 3)} | {a['overlap_houses']} | "
            f"{_f(a['T2_facet_iou_mean'], 2)} ({a['T2_n']}) | {_f(a['T1_squares_abs_err_pct_median'], 1)} ({a['T1_n']}) | "
            f"{_f(a['runtime_median_s'], 1)} |")


HEAD = ("| group | n | automation | fit_all | fit_covered | coverage | facets | <30 sqft | <3 ft | axis 7deg | false lvl | "
        "overlap houses | T2 IoU (n) | T1 |sq err| % (n) | runtime s |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def render(summary: dict[str, Any], recs: list[dict[str, Any]]) -> str:
    """tables.md: the run header, the overall row, per-stratum rows, verdict and failure mixes, T3, compare and gates."""
    o = summary["overall"]
    head = (f"# roof-eval: engine {summary['engine']}, split {summary['split']}, {summary['n']} houses, "
            f"{summary['wall_s']} s wall")
    lines = [head, f"digest `{summary['digest'][:16]}`, scorer v{summary['scorer']}", "",
             "Medians over houses with a result. Automation = share of houses with a result and verdict ok.", "", HEAD,
             _row("ALL", o)]
    for k, grp in summary["by"].items():
        lines += ["", f"### by {k}", "", HEAD] + [_row(v, a) for v, a in grp.items()]
    lines += ["", f"verdicts: {o['verdicts']}", f"parcel_match: {o['parcel_match']}", f"engine failures: {o['failures']}",
              f"price |delta| % median: T1 {_f(o['price_abs_pct_median_T1'], 1)}, T2 {_f(o['price_abs_pct_median_T2'], 1)}"]
    if summary.get("t3"):
        t = summary["t3"]
        lines.append(f"T3 aggregate, PRICED area (n={t['n']}): median result/contractor squares {t['median_ratio']:.3f}, "
                     f"90% interval [{t['lo90']:.3f}, {t['hi90']:.3f}]")
    if summary.get("t3_drawn"):
        t = summary["t3_drawn"]
        lines.append(f"T3 aggregate, DRAWN area (n={t['n']}): median {t['median_ratio']:.3f}, 90% interval [{t['lo90']:.3f}, {t['hi90']:.3f}]")
    lines.append(f"T2 houses with two labels: {o['T2_two_label_houses']}, label runs that disagree (IoU < 0.60): {o['T2_label_disagree']}")
    lines.append(f"priced totals read from the engine in {o['priced_from_totals_houses']} houses; "
                 f"{o['priced_inconsistent_houses']} houses with inconsistent priced totals")
    if summary.get("canaries"):
        lines += ["", "## canaries (never counted as evidence)", "", "| id | status | verdict | fit_all | fit_covered | coverage | facets | T2 IoU |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {c['id']} | {c['status']} | {c['verdict']} | {_f(c['fit_all'], 2)} | {_f(c['fit_covered'], 2)} | {_f(c['coverage'], 2)} | "
                  f"{_f(c['facets'], 0)} | {_f(c['T2_iou'], 2)} |" for c in summary["canaries"]]
    if summary.get("price_rules"):
        pr = summary["price_rules"]
        lines.append(f"price rules: {pr['file']}" + ("  *** EXAMPLE RULES (fake prices): price deltas are for wiring only ***" if pr["example"] else ""))
    if "compare" in summary:
        c = summary["compare"]
        body = (f"paired {c['n_paired']}, flagged {c['n_flagged']} ({100 * c['flagged_share']:.1f}%), "
                f"median |area change| {_f(c['median_abs_area_pct'], 2)}%; reasons {c['reasons']}")
        lines += ["", f"## compare with baseline {c['baseline']}: {'PASS' if c['pass'] else 'FAIL'}", body]
        lines += [f"- {f['id']}: {', '.join(f['why'])}" for f in c["flagged"][:60]]
    if "gates" in summary:
        lines += ["", "## gates", "", "| gate | n (with value) | value | need | result |", "|---|---|---|---|---|"]
        lines += [f"| {g['name']} | {g['n']} ({g['n_value']}) | {_f(g['value'])} | {g['op']} {g['threshold']} | "
                  f"{'PASS' if g['passed'] else 'FAIL'} {g['note']} |" for g in summary["gates"]]
    bad = [r for r in recs if r["engine"]["status"] != "ok" or r.get("status") == "score_error"]
    if bad:
        lines += ["", "## houses without a result", ""]
        lines += [f"- {r['id']}: {r['engine']['status']} {r.get('error', '')} {r['engine']['stderr_tail'][-120:]!r}" for r in bad[:60]]
    return "\n".join(lines) + "\n"
