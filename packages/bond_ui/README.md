# bond_ui

Shared Flutter design tokens, theme and widgets for the bond app family. Nothing here opens a popup: dialogs, sheets, dropdown buttons, snack bars and tooltips are banned and tested for.

## Tokens model
- `BondTokens` is a `ThemeExtension` holding colours and the font: `ink body muted line lineStrong ground surface onFill shadow`, five tones (`accent danger positive caution info`, each a `BondTone` with `base press wash soft`), `fontFamily`, `fontPackage` and `personPalette`.
- `BondSpace`, `BondRadius`, `BondText` (sizes and weights) and `BondLayout` (breakpoints and fixed sizes) are plain constants, because spacing is not brand specific.
- Widgets read `BondTokens.of(context)`. With no extension installed it returns `BondTokens.fallback` (neutral greys, one blue), so a widget renders anywhere.

## Filling the tokens once
An app builds one `BondTokens` and installs it at the top of its widget tree:

```dart
const tokens = BondTokens(
  ink: ..., body: ..., muted: ..., line: ..., lineStrong: ..., ground: ..., surface: ...,
  accent: BondTone(base: ..., press: ..., wash: ..., soft: ...),
  danger: ..., positive: ..., caution: ..., info: ...,
  fontFamily: 'YourFont', fontPackage: 'your_app',
);
MaterialApp(builder: (context, child) => BondScope(tokens: tokens, child: child!));
```

`BondTheme.build(tokens)` returns the Material 3 `ThemeData` if you prefer to pass it to `MaterialApp.theme`. An app that already has `XSpace`-style constants keeps them as aliases of `BondSpace` (`static const double s8 = BondSpace.s8;`) so call sites do not change.

## Labels
`BondLabels` holds every string a primitive shows, in English. Wrap a subtree in `BondLabelsScope(labels: ..., child: ...)` to translate. There is no `intl` dependency; month and weekday names are in the labels.

## Semantics ids
Every interactive widget takes `String? semanticsId` and wraps itself with `bondSemantics(id: ...)`, which sets `Semantics(identifier: ...)` for test drivers. Groups derive ids as `'<id>-<value>'` (`bondSemanticsOption`): select options, segmented cells, date days (`<id>-day-2026-11-08`), time chips, confirm buttons (`-confirm`, `-cancel`, `-undo`).

## Primitives
| Widget | Notes |
| --- | --- |
| `BondButton`, `BondIconButton`, `BondPressable` | variants, loading, wrap, 48 px hit area |
| `BondTextField`, `BondSearchField`, `BondInlineField` | label above, inline error, soft counter |
| `BondSelect` | chips, segmented, radio list, expanding inline list |
| `BondSegmented`, `BondChip`, `BondStatusChip` | choices and statuses |
| `BondDateField`, `BondTimeField` | in-page calendar grid and time entry, no pickers |
| `BondConfirm` | inline arm, confirm, optional undo, arm timeout |
| `BondBanner`, `BondActionRow`, `BondListRow`, `BondCard` | page-flow surfaces |
| `BondAvatar`, `BondPhoto`, `BondDashedBorder` | display |

## Shell and components
Inline only: nothing opens a dialog, sheet or menu. Colours come from BondTokens. Words come from BondLabels (set once with BondLabelsScope). Interactive pieces take semanticsId.

| Widget | Role |
|---|---|
| BondSideNav, BondNavGroup, BondNavDestination | Sidebar. selectedId is a plain string. Groups fold inline. rail shows icons only. |
| BondBottomNav | Phone bottom bar with badges. Each item has a semanticsId. |
| BondAccountCard, BondAccountRow | Signed-in person. Expands in place. |
| BondRailCard, BondRightRail | Cards and a column beside the content. |
| BondPageHeader, BondCrumb | Title, subtitle, actions, breadcrumbs. |
| BondTabs, BondTab | Underlined tabs. Scrolls sideways when narrow. |
| BondTable, BondColumn | Aligned columns. Stacks each row below 540 wide. |
| BondTimelineList | Time, tone dot, title, body. |
| BondPersonChip | Palette-coloured pill. Dashed when unassigned. |
| BondMessagePreview | Switch between message variants. |
| BondEmailSignIn | Fields, inline validation, callbacks only. |
| BondGoogleSignInButton | Button and notice. The page owns the call. |
| BondEmptyState, BondLoadingState, BondErrorState | Inline page states. |
| BondStaleBanner | "Not updated since ...". The caller formats the time. |
| BondDeactivated, BondStartupFailed | Whole-page inline states. |
| BondLogoMark | Places the app's own logo widget at a size. |

## Tests
```
make -C packages/bond_ui test T=test/primitives/bond_button_test.dart
make -C packages/bond_ui analyze
```
Widget tests use `bond_test_support`: `pumpApp`, `setPhone` and `expectNoOverlays`.
