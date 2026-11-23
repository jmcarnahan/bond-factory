# Changelog

## Unreleased
- Flat seams (roof_measure 0.5.1): `EdgeType.flatSeam` (`flat_seam`), a seam between two flat sections at one level. Drawn
  as a thin dark line (1.2 px, `0xFF5A5A5A`), never labelled, never in the legend, `lengths_ft` or the edge total
  (`RoofTotals.recompute` skips it). Flat-typed facets are outlined in the same stroke on the length diagram (was light grey,
  1 px); other facets draw as before, and every 0.2 and 0.3 envelope draws as before; a 0.4 envelope's flat facets gain the seam-coloured outline. BREAKING only for hosts that `switch` over `EdgeType` without a
  default.
- A `level_change` edge is labelled with its length like every other edge ("24"), plus the step when the jump is 3 ft or
  more ("24, 5 ft step"). The old label that replaced the length with "Step <jump>" is gone; its key `level_change_jump`
  stays for adopters but is no longer used. New `RoofLabels` keys `legend_flat_seam` and `level_change_step` (93 keys now).
- Envelope 0.4 (`docs/contract-0.4.md`), additive: old 0.2 and 0.3 envelopes parse, write back and draw exactly as before
  (scene digests of every shipped fixture are identical to the previous commit).
  - BREAKING for hosts that `switch` over `EdgeType` without a default (it has two more values) and for code that assumes
    `RoofTotals.lengthsFt.length == 10`. Additive otherwise. Version is decided at release.
  - `RoofFacet` gains nullable `roofType` (`flat` | `pitched`), `pitchFit`, `pitchSigma`, `borderline`, `supportedPct`,
    `points`, `rmsFt`, `planEq` (`[a, b, c]`) and the getters `isFlatRoofType`, `isBorderline`; written back only when present.
    `RoofFacet` and `RoofEdge` now compare by value (`==`, `hashCode`).
  - `EdgeType` gains `flatEdge` (`flat_edge`) and `levelChange` (`level_change`), placed after the ten old values;
    `EdgeType.legacy` lists the old ten, `isNew04` marks the new two. `RoofEdge.jumpFt` (`jump_ft`). An unknown edge type
    still reads as `unspecified` (noted in `parseNotes`). `RoofTotals.lengthsFt` now always holds all twelve types;
    `toJson` writes the two new ones only when they are not zero.
  - `RoofEngineTotals` (with `RoofComplexity`): the new totals keys (`roofing_pitched_sqft`, `roofing_flat_sqft`,
    `roofing_*_squares`, `low_slope_confirm_sqft`, `area_sqft_wall_line`, `area_sqft_roof_edge`, `outline_perimeter_wall_ft`,
    `overhang_ft_median`, `flat_edge_ft`, `level_change_ft`, `complexity`, and the cost-sheet keys `planes_surface_area_sqft`,
    `planes_pitch_weighted`, `outline_perimeter_ft`), all nullable, on `RoofEnvelopeTotals.engine` and `RoofTotals.engine`.
  - `RoofEngineQuality` (`RoofModel.quality`: engine, fitAll, fitCovered, coverage, supportedPct, densityPtsM2, parcelMatch,
    outlineSource, verdict, raw) and `RoofBuilding` (`RoofModel.building`: parcelId, outlineId, outlineCentroid, chosenBy).
  - Diagrams: a facet typed `flat` is drawn with a neutral fill and a hatch (plain `LinePrim`s, so SVG and PDF need nothing new);
    a borderline facet gets an orange outline and, in the area diagram where it fits, a third label line (`low_slope_marker`);
    the length legend adds "Flat roof edges" and "Level changes" only when the model has them; a level change edge is drawn
    heavier and labelled with its jump (`level_change_jump`, "Step 2ft 6in"). New `DiagramStyle` fields `flatRoofFill`,
    `hatchColor`, `borderlineStroke`, `edgeWidthScale`; new `RoofLabels` keys `legend_flat_edge`, `legend_level_change`,
    `low_slope_marker`, `level_change_jump`, `totals_roofing_pitched`, `totals_roofing_flat`, `totals_low_slope_confirm`, `totals_priced_area`, `totals_as_drawn` (nine new keys in all).
  - `Scene.regions` (`SceneRegion`: facet id and outline in scene pixels) and `Scene.facetAt(point)` let a host find the facet
    under a tap. `ReportLayout.legendRowsFor(count)`.
  - Changed test: `model_test.dart` "pitch buckets" expected `lengthsFt.length == 10`; it now expects `EdgeType.values.length`.
- Tests only: a planes-only envelope (`fixtures/roof_planes_only/`, no facets or edges) parses, and `LengthDiagram`,
  `AreaDiagram` and `SummaryBlock` build on it without throwing. No library change.
- Licence: MIT (LICENSE file added). It was GPL-3.0-or-later with the rest of the repository;
  no code changes.

## 0.2.0 (2026-11-11)
- Added `RoofMeasurement` (0.2 envelope: model, `RoofEnvelopeTotals`, `RoofVerification`, `RoofVerdict`,
  confidence score, warnings, `warningCodes`, `extra`) with `fromJson`, `toJson`, `fromModel` and
  `parseAny` (envelope or bare 0.x model).
- `RoofMeasurement.generatedAt` is nullable (null when absent or unparseable; omitted from `toJson`). `confidence` is clamped to 0..1, contracts other than `bond.roof_model/0.x` are rejected, and an unknown verdict string is kept in `RoofVerification.verdictRaw`.
- Added `RoofTotalsVariants` (drip edge eave / eave + rake, ridge cap ridge / ridge + hip).
- Added `RoofLabels`: every user-visible string with English defaults, `fromMap`, `toMap`, `copyWith`,
  `keys`, `fill`. `fromMap` and `copyWith` accept `Map<String, String?>`; null, empty and whitespace-only values keep the English default. `LengthDiagram`, `AreaDiagram`, `SummaryBlock`, `scenesToPdf`, `feetInches` and
  `pitchLabel` take `labels`. The "n/a" cells are chosen by a null value, not by text.
- Added `ReportLayout { wide, compact }`; the three builders take `layout` and default their size to
  the layout's design size (compact: 400 x 500, two-column legend and figures, text at least 14 px).
  `width` and `height` of the builders are now nullable.
- Tolerant parser: unknown edge type, facet kind, block form and `lengths_ft` key no longer throw; they map
  to `unspecified`, by pitch, `flat` and `RoofTotals.extraLengths`, and are listed in `RoofModel.parseNotes`.
- `RoofModel` split into `model.dart`, `model_parts.dart` and `totals.dart` (public names unchanged).
- Breaking: the contract palette constant on `DiagramStyle` is now `DiagramStyle.report` (renamed).
- `vector_math` constraint `^2.4.0`.

## 0.1.0 (2026-11-07)
- Initial public layout.
- Renamed from its pre-public working name.
- Consumed by git SHA, not by tag.
