# bond_roof

Role: pure Dart roof model. JSON `bond.roof_model/0.1` models and the 0.6 envelope (older shapes still open and draw less), totals, diagram scenes, labels, SVG/PDF export.
Consumed by bond_roof_ui and by apps (pinned by commit).
Contract: docs/contracts/roof_model.md

## Key files
- lib/bond_roof.dart — barrel (everything public except PDF)
- lib/roof_pdf.dart — separate PDF library (keeps `pdf` out of non-printing apps)
- lib/src/model.dart, model_parts.dart, model_facet.dart, totals.dart — RoofModel, facets/edges/holes/objects, totals (tolerant parser)
- lib/src/engine_totals.dart, figures.dart — the 0.6 totals keys (nullable); the figures of one roof and the totals rows
- lib/src/measurement.dart — the envelope; object_draw.dart — chimney and lantern marks
- lib/src/labels.dart, labels_defaults.dart — RoofLabels (all strings); report_layout.dart — wide / compact
- lib/src/scene.dart — device-independent drawing primitives
- lib/src/length_diagram.dart, area_diagram.dart, summary_block.dart — the three report scenes
- lib/src/layout.dart, polylabel.dart, metrics.dart — label placement and text width
- lib/src/format.dart, style.dart — number formats, colours, sizes; svg.dart, pdf_export.dart — scene to SVG / PDF
- test/support.dart — sample loader, old-fixture loader, `unknownEnvelopeKeys`; tool/check_envelope.dart — the same check on files

## Commands
- One test: `make test T=test/model_test.dart`
- All tests: `make test`; analyze: `make analyze`
- Render fixtures (both layouts) to tmp/render/: `make render`

## Rules
- No Flutter imports. No literal user-visible strings in scene code: add a key to labels_defaults.dart.
- The reference fixture is `../../fixtures/roof_engine/roof_measurement_0.6_sample.json`; old shapes come from `../../fixtures/` via test/support.dart.
- Changing the schema id or a field is a contract change: update docs/contracts/roof_model.md and the service.
