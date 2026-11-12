# bond_ui
Role: Shared Flutter design tokens, theme, labels and widgets for the bond app family. Core (tokens, theme, primitives) plus `shell/` and `components/`.

## Key files
- `lib/bond_ui.dart`: the barrel; nothing else is imported by apps.
- `lib/src/tokens/`: `BondTokens` (colours, font), `BondShape` (themable radii, read as `BondTokens.of(context).shape`), `BondSpace`, `BondRadius` (deprecated rN aliases, `pill`), `BondText`, `BondLayout`. Raw colours live only here.
- `lib/src/theme/`: `BondTheme.build`, `BondScope` (the one injection point).
- `lib/src/labels.dart`: `BondLabels`, every string a widget shows. `lib/src/semantics.dart`: `bondSemantics`.
- `lib/src/primitives/`: the `Bond<Name>` primitive widgets (plus small internal helpers: confirm line, date calendar, date format). Tests in `test/primitives/`.

## Commands
- `make test T=test/primitives/bond_button_test.dart` (one file)
- `make analyze`

## Rules
- No popups, dialogs, modal sheets, dropdown buttons, snack bars or tooltips; show state inline. `test/source_guards_test.dart` enforces it.
- Colours only from `BondTokens.of(context)`; no `Colors.` or `Color(0x` outside `lib/src/tokens/`.
- Every interactive widget takes `String? semanticsId` and wraps itself with `bondSemantics`.
- Strings go through `BondLabels`; no intl, riverpod, go_router or localizations.
- Tests import `package:bond_ui/src/...` files, not the barrel (only `barrel_test.dart` does).
- No codegen. Barrel and CHANGELOG.md updated on every public API change. 300-line cap per file.
