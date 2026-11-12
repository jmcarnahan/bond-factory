# Changelog

## Unreleased
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
