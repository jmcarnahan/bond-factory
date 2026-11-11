# Changelog

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
