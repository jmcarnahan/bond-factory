# bond_roof_ui

Role: Flutter widgets that draw bond_roof scenes, plus print and share (via `printing`).
Depends on bond_roof (path) and `printing`.
Contract: docs/contracts/roof_model.md

## Key files
- lib/bond_roof_ui.dart — barrel
- lib/src/scene_painter.dart — paints a Scene on a canvas, scaled to fit
- lib/src/report_strip.dart — three diagrams stacked, inline Print and Save PDF, status line
- lib/src/report.dart — report pages as scenes; print and PDF share/download
- lib/src/tokens.dart — layout and colour tokens for these widgets
- assets/fonts/Roboto-Regular.ttf — PDF font (license beside it)
- test/roof_diagram_view_test.dart

## Commands
- One test: `make test T=test/roof_diagram_view_test.dart`
- All tests: `make test`; analyze: `make analyze`

## Rules
- The no-popups gate applies: status is inline, no dialogs or snackbars. OS print/share UI is allowed.
- Drawing logic belongs in bond_roof scenes; this package only paints and hands off.
- Raw colours and sizes live in lib/src/tokens.dart.
