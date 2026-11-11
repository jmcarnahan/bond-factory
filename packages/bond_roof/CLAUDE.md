# bond_roof

Role: pure Dart roof model. JSON `bond.roof_model/0.1` models and the 0.2 envelope, totals, diagram scenes, labels, SVG/PDF export.
Consumed by bond_roof_ui and by the roof_measure service's contract tests.
Contract: docs/contracts/roof_model.md

## Key files
- lib/bond_roof.dart — barrel (everything public except PDF)
- lib/roof_pdf.dart — separate PDF library (keeps `pdf` out of non-printing apps)
- lib/src/model.dart, model_parts.dart, totals.dart — RoofModel, blocks/facets/edges/holes, totals (tolerant parser)
- lib/src/measurement.dart, measurement_parts.dart, totals_variants.dart — 0.2 envelope, verification, paired variants
- lib/src/labels.dart, labels_defaults.dart — RoofLabels (all strings); report_layout.dart — wide / compact
- lib/src/scene.dart — device-independent drawing primitives
- lib/src/length_diagram.dart, area_diagram.dart, summary_block.dart — the three report scenes
- lib/src/layout.dart, polylabel.dart, metrics.dart — label placement and text width
- lib/src/format.dart, style.dart — number formats, colours, sizes; svg.dart, pdf_export.dart — scene to SVG / PDF
- test/support.dart — fixture loader

## Commands
- One test: `make test T=test/model_test.dart`
- All tests: `make test`; analyze: `make analyze`
- Render fixtures (both layouts) to tmp/render/: `make render`

## Rules
- No Flutter imports. No literal user-visible strings in scene code: add a key to labels_defaults.dart.
- Fixtures come from `test/fixtures/` and `../../fixtures/` via test/support.dart.
- Changing the schema id or a field is a contract change: update docs/contracts/roof_model.md and the service.
