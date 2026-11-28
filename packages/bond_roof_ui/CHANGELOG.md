# Changelog

## Unreleased
- Library 0.7.0 (`docs/contract-0.7.md`): `RoofTotalsTable` prints the new rows of `totalRows` from `bond_roof` when the roof has them (rooftop units, lantern sides, lantern hips, headwall all round a raised roof); nothing in this package changed besides its tests, which read the 0.7 sample.
- Roof accuracy round (0.6 contract; BREAKING for hosts that read the old totals): `RoofTotalsTable` prints `totalRows` of `bond_roof`: only the
  rows the roof has, sidewall and headwall flashing, eave + rake, exposed edges, ridge + hip, chimneys. The drip edge and ridge cap
  variants, the verification line, the "Total roofing area" / "As drawn" headline and the pitched / flat rows tied to the 0.4 keys are gone.
- Test: `roof_proof_test.dart` paints the length and area diagram of the 0.6 sample through the real painter.
- `RoofTotalsTable`: the "ridge + hip" row shows the drawn ridge + hip, so it is never smaller than "ridge only" (it showed the priced value).
- Envelope 0.4: `RoofDiagramView(scene, {fit, onFacetTap})` and `RoofReportStrip(..., onFacetTap)` report the id of a tapped
  facet (the package draws nothing in response; the host attaches inline controls). New `sceneFit` and `facetIdAt`.
  Flat facets are painted hatched and borderline facets outlined (the scene carries it, see `bond_roof`).
- `RoofTotalsTable`: with the 0.4 `roofing_*` totals and `planes_surface_area_sqft` the headline is the PRICED area ("Total roofing area", equals pitched + flat) and the drawn area is its own row ("As drawn (to the roof edge)"). Old envelopes keep "Total area".
- `RoofTotalsTable` lists "Pitched roofing" and "Flat roofing" (square feet and squares) on separate rows, and
  "Low slope, confirm" when there is such area, only when the envelope carries the `roofing_*` totals; nothing changes without them.
- Licence: MIT (LICENSE file added). It was GPL-3.0-or-later with the rest of the repository;
  no code changes.

## 0.2.0 (2026-11-11)
- `RoofReportStrip` takes `model` or `measurement` as named arguments (breaking: the model was positional),
  plus `labels`, `showActions`, `showTotals` and `onStatus`. Width under 600 px builds the compact layout;
  scenes are cached per model, labels and layout.
- Added `Share PDF` next to Print and Save PDF; status text stays inline.
- Added `RoofTotalsTable(measurement, {labels})`.
- `RoofReport.pages` takes `labels` and `layout`; added `RoofReport.pdfBytes`, `printReport`, `saveReport`,
  `shareReport` (the top-level `printReport` and `shareReport` remain).
- Breaking: `RoofUiTokens.pdfTitle` and `RoofUiTokens.pageTitles` moved into `RoofLabels`; added
  `RoofUiTokens.compactBreakpoint`.

## 0.1.0 (2026-11-07)
- Initial public layout.
- Renamed from its pre-public working name.
- Consumed by git SHA, not by tag.
