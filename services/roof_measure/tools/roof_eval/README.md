# roof_eval

Generic scorer and regression harness for roof results. No data lives here: point `ROOF_EVAL_DATA` at an unpacked
regression set (layout in `data.py`). Run from `services/roof_measure`.

| Target | What it does |
|---|---|
| `make roof-eval ENGINE=... [SPLIT=tuning] [BASELINE=x] [GATES=g.json] [TWICE=1]` | run, score, compare, gate; exit 1 on a failed gate or comparison |
| `make roof-baseline NAME=x CONFIRM=1 [RUN=dir]` | freeze a run under `<data>/baselines/x` (an old one is moved aside) |
| `make roof-blind N= SEED= CAND="a=<dir> b=baseline:x" OUT=<dir> KEY=<file>` | anonymous sheets (X/Y/Z); the key goes elsewhere |
| `make roof-blind-score GRADES=grades.tsv KEY=key.json` | A/B/C counts with Wilson 95% intervals |
| `make roof-synth ENGINE=... [ONLY=substr] [GATES=g.json]` | gate 9 over the synthetic roofs (tolerances from `synth_gates` in gates.json); `ENGINE=oracle` returns the exact roof and exits 1 by design (it answers below 4 pts/m2); `ARGS=--selftest` exits 0 iff only those cases fail |
| `make roof-sweep HOUSES=<dir> ENGINE=...` | truth-free run: automation, verdicts, parcel match, failures, runtime |

Engines are commands: `ENGINE="<cmd> {house_dir} {out_json}"`, or the adapters `library` (stored envelope; one datum
constant per building, no per-facet refit; `library:ground` takes it from the ground ring) and `results-dir:<dir>`
(existing result.json files; `ROOF_EVAL_SLUG_MAP` maps ids to folder names). Thresholds are data: `gates.example.json`
(see `gates/`), unit prices: `price_rules.example.json` (fake). Metric definitions are the docstrings of `m_fit.py`,
`m_shape.py`, `m_truth.py`; the result contract is the CONTRACT-1 result.json (facets with planes in metres, typed edges).

## Known limit of `fit_all`
Reference points follow rule ref-v1 (non-ground returns more than 1.5 m above local ground inside the wall outline plus
1.2 m). Tree canopy that overlaps the roof is inside that rule and no facet can fit it, so `fit_all` is depressed on such
houses, equally for every engine (the synthetic tree cases show 0.77-0.87 for an exact answer). A cell-height cutoff does
not remove canopy (tested: no effect); a planarity rule was judged not worth its cost. Therefore thresholds on `fit_all`
are set from tuning percentiles, and `fit_covered` and `coverage` are always reported beside it.

## Other notes
- Run directories default to `out/roof-eval/<engine>-<split>` (`ROOF_EVAL_OUT` moves the base, `OUT=` sets one run);
  `TWICE=1` runs the whole evaluation twice and exits 1 unless the digests are identical.
- A `level_change` edge is false when the jump measured from the points is under 0.3 m (the contract-0.4 threshold).
- `min_n` in a gate counts houses that have a value for the metric (reported as `n_value`), not the whole population;
  filter T2 gates with `where: ["tiers=T2"]`.
- Gate 9 below 4 pts/m2 passes only an engine that ran, returned no facets and said `lidar_too_sparse`.
- Blind keys carry, per letter, whether the engine labelled the result ok; `blind-score` reports a `labelled_ok` group
  (plan gate 4). A candidate without a drawing shows a neutral "no drawing" panel (a blank panel is still visible).
- Price delta compares the engine's area-weighted pitch with a truth file's predominant pitch; near a multiplier row edge
  that difference alone can move the material line.

## Hardening (adversary round)
- **Engines see sanitised input only.** The engine runs on a temp copy with `points_wide.npy`, `points.npy`, `footprint.json` and
  a minimal `meta.json` (frame, outline_source, parcel_match). Never reference points, envelope, truth or baselines. Only the
  `library` adapter (it converts the stored envelope by design) gets the real dir.
- **Edges are recomputed from the facets** (`edges_re.py`): shared boundaries typed by plane geometry and by the jump measured
  from the points (level change >= 0.3 m), outline edges eave/rake/flat_edge. Perimeter, ridge+hip, valley, level-change and
  cleanliness metrics use the recomputed set; the engine's own list only feeds `edge_list_disagreement_ft`, the false level
  changes and `unmarked_level_change_ft` (a verified jump the engine did not type level_change). Jumps that cannot be measured
  (< 5 points a side) are `level_change_unverified_ft`, reported apart. Individual eave/rake feet are recomputed too; a
  pitched facet's level HIGH outline edge (a shed's) is `rake` with `high_edge` (contract convention), never ridge or eave.
- **One roof, one basis:** every tier is compared with the DRAWN roof (the facets and the recomputed edges); the engine's
  totals keys are not read (0.6.0 retired the priced-versus-drawn split). Gate 7a (the contractor-squares interval contains
  1.00) is a REPORTED figure, not a gate (`report_only` in the gate file).
- **Over-segmentation and padding:** `facet_count_ratio` (vs manifest `facet_count_ref`), `facets_per_1000sqft`,
  `mergeable_neighbour_share` (adjacent facets coplanar within 0.07 m and 3 degrees), `unsupported_facet_area_share` (drawn
  area with no reference point within 0.5 m), `outside_outline_area_share` (report-only: no threshold in 3.7a).
- **Malformed output is `invalid`** (schema in `validate.py`), distinct from a refusal; the gate "invalid or crashed = 0" counts it.
- **No gates, no pass:** `roof-eval` picks `gates/<split>.json`; with none it prints NO GATES EVALUATED and exits 3 unless `NO_GATES=1`.
- Gate files encode plan 3.7a. `negative.json` passes any engine that labels no negative house ok. `heldout.json` equals
  `tuning.json` but with insufficient labelled houses failing.

## Judge findings (held-out round)
- `--twice` now exits 1 when a gate or comparison fails in either run (identical digests used to mask it).
- Gate 3h counts only INDEPENDENT references: manifest `facet_count_src` in {vision_label, vendor, manual}; houses with src
  `library` or none are excluded, `min_n` 10 applies. Fill `facet_count_src` honestly.
- Canaries (`canary: true`) are never in a gate population or in the aggregate tables; `tables.md` and `summary.json` carry a
  separate canary section.
- Pooled strata (plan 3.7a): complex = complexity >= 10; flat+mixed = flat, mixed or commercial and not complex; pitched = rest.
- blind-score accepts grade R (no drawing: counted apart, A/B/C shares are over A+B+C) and note columns (`X_note`).
- Gate 7b with no frozen library baseline computes ENGINE=library on the same houses (needs the stored envelopes in the data
  root); otherwise ship `baselines/library-0.4.0/metrics.json` (made by `roof-baseline` on that root).
- The price table says EXAMPLE RULES when the fake example file is used; pass real rules with `PRICE=<file>`.
- T2: `truth.llm_vision*.json` files; two label runs of a house get an IoU agreement and a `disagree` flag below 0.60 (kept, not dropped).

## Labels, the shape gate and `flat_seam` (roof-tidy, 2026-11-23)
- **Label tool** (`tools/roof_eval/label/`, a port of the labelling code with no address handling): houses are opaque ids; a work
  folder holds `houses.tsv` (columns `id`, `folder`, optional `split`, `strata`), `runs/<id>/<tag>/`, `truth/<id>/`, `spend.tsv`,
  `labels.tsv`. `python -m tools.roof_eval.label compare|relax --work-dir D` never touch the network. `run` and `one` SPEND
  money on the Anthropic API and refuse to start without BOTH `--spend-cap USD` (a total over the whole ledger, earlier runs
  included) and `--confirm-spend`; the key is read only from the environment (`ANTHROPIC_API_KEY`), children get a minimal
  environment. `one --render-only` and `--dump-request` spend nothing. No aerial-photo fetch exists any more.
- **Agreement rule (plan D4):** two runs per house; accepted when areas differ <= 8 % and the two-sided facet IoU is >= 0.6;
  `accepted_high` when both runs have >= 85 % of in-facet returns within 12 cm, else `accepted_medium`; else
  `rejected_disagree`. The merged `truth.llm_vision.json` carries `confidence` and `fit12_pct: [r1, r2]`. The fit figure is a
  tag, never a pass/fail. (The old "a run was not self-corrected" reason is gone: only the two numbers decide.)
- **Shape gate (gate 6, agg `t2_shape`):** reports the mean two-sided facet IoU on `high`, on `medium` and on `all` labels, GATES
  on `all` (>= 0.60, `min_n` 10), and FAILS LOUDLY when high and medium differ by more than 0.15 (`max_conf_gap`). Below
  `min_n` it FAILS on both tuning and held-out (a dropout must never turn it into a silent pass; the generic `on_insufficient: skip`
  mechanism still exists for other gates and prints SKIPPED, NOT EVALUATED). Labels with no confidence tag count in `all` only.
- **`flat_seam` edges** (library 0.5.1): a known edge type, drawn but never counted. `Roof.counted_edges` drops it; lengths,
  the false level-change share (numerator and total) and cleanliness edge counts ignore it.
- **Shape-gate confidence gap needs n >= 3** in BOTH the high and the medium group; below that the note says "confidence gap not
  evaluated (n_high=.., n_medium=..)" and the gate decides on "all" alone (`min_group_n`).
- **Flat/flat seams in gate 3l** are judged by `seam_check.strip_step` (strip medians of the raw returns at 12 stations, 0.4-2.5 m
  from the seam, step = medians differ >= 0.3 m at >= 70 % of usable stations; fewer than 4 usable stations = not evaluable, counted
  in no numerator), never by the engine's own rule: UNMARKED = step by strip medians while the engine did not type level_change;
  FALSE = engine level_change with no step by strip medians. Other seams keep the point-jump recipe.
- Label decisions (area difference, facet IoU, the 85 % tag) use UNROUNDED values; the displayed columns in `labels.tsv` are rounded.
