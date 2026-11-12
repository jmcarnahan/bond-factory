# Migrating to bond_ui

Tokens, theme, labels and 37 widgets (`packages/bond_ui`, Flutter): 19 primitives, 5 shell, 13 components. Colours and
fonts live in a `BondTokens` theme extension; spacing, radius and type scale are constants. Legend: `docs/migration/README.md`.

## 1. What it replaces
Paths are under `flutterui/packages/<ui>/lib/src/` (A `avalon_ui`, P `pt_ui`).

| App | Goes away or shrinks | Stays app-side |
|---|---|---|
| A | `primitives/` 19 files 2,408 lines, `shell/` 5 files 576, 13 of 31 `components/` 949, `tokens/av_space.dart` 39 (becomes a typedef), `test/source_guards_test.dart` 112, `test/tokens/token_values_test.dart` 95, the 2 `DropdownButton` lines in `flutterui/tool/allowlist_popups.txt` | the other 18 components (conversation, kanban, money, line_items, voice, ...), `av_lookahead`, `av_text_link`, `av_undo_line`, `av_command_bar`, the other tokens (`AvColors`, `AvText`, `AvCrewColors`), `theme/` (shrinks), `AvL10n` |
| P | `primitives/` 18 files 2,163, `shell/` 5 files 527, `components/` 13 files 929, `tokens/pt_space.dart`, its two guard tests (119, 125) | other tokens (`PtColors` adds `*OnBlack` tones), `theme/`, `PtL10n` |
| S | phone `mobile/crm_proposals/lib/ui/` 39 files 4,925 (colours `tokens/sbel_colors.dart` 100, `sbel_tones.dart` 270; `inline_confirm` 128, `sbel_date_field` 354) | later: needs a token map first; web last |

## 2. The adapter (A; P is the same with `Pt`, `pt_ui`)
`flutterui/packages/avalon_ui/lib/src/tokens/bond_aliases.dart`. Spacing has the same names, so a typedef keeps all
2,420 `AvSpace` uses (P: 1,163 `PtSpace`) compiling, including in `const` contexts:

```dart
import 'package:bond_ui/bond_ui.dart';
import 'av_colors.dart';
import 'av_crew_colors.dart';
import 'av_tone.dart';

typedef AvSpace = BondSpace;
// AvRadius, AvText, AvShadows, AvLayout stay as they are: names differ and the app's own widgets still use them.
// One BondTone per family; A has no separate press/soft for positive, caution, info, so base and wash repeat.
const _red = BondTone(base: AvColors.red, press: AvColors.redPress, wash: AvColors.redWash, soft: AvColors.redSoft);
const avTokens = BondTokens(
  ink: AvColors.ink, body: AvColors.body, muted: AvColors.muted, line: AvColors.line,
  lineStrong: AvColors.lineStrong, ground: AvColors.ground, surface: AvColors.surface,
  accent: _red, danger: _red, // A's primary button and its error colour are both the brand red
  positive: BondTone(base: AvColors.positive, press: AvColors.positive, wash: AvColors.positiveWash, soft: AvColors.positiveWash),
  caution: BondTone(base: AvColors.caution, press: AvColors.caution, wash: AvColors.cautionWash, soft: AvColors.cautionWash),
  info: BondTone(base: AvColors.info, press: AvColors.info, wash: AvColors.infoWash, soft: AvColors.infoWash),
  onFill: AvColors.onFill, shadow: AvColors.shadow, fontFamily: 'Figtree', fontPackage: 'avalon_ui',
  personPalette: AvCrewColors.all,
);

extension AvToneRole on AvTone { // 166 uses of AvTone.red keep working; black has no role
  BondToneRole? get role => switch (this) {
        AvTone.neutral || AvTone.black => null,
        AvTone.info => BondToneRole.info,
        AvTone.caution => BondToneRole.caution,
        AvTone.red => BondToneRole.danger,
        AvTone.positive => BondToneRole.positive,
      };
}
// AvL10n is the app's generated localizations class.
BondLabels avLabels(AvL10n? l) => l == null ? const BondLabels() : BondLabels(
      cancel: l.common_cancel, confirm: l.common_confirm, dismiss: l.common_dismiss, errorTitle: l.common_error,
      loading: l.common_loading, nextMonth: l.common_nextMonth, previousMonth: l.common_previousMonth,
      sent: l.common_sent, undo: l.common_undo, retry: l.stale_retry, staleUnknown: l.stale_unknown);
```

`AvScope` keeps the `Localizations` delegates and installs tokens and labels below them (`theme/av_scope.dart`):
```dart
child: Builder(builder: (context) => Theme(
  data: AvTheme.build().copyWith(extensions: [avTokens]), // or BondTheme.build(avTokens)
  child: BondLabelsScope(labels: avLabels(maybeL10n(context)), child: child))),
```

A widget whose old API still compiles is a typedef (`typedef AvAvatar = BondAvatar;`; the changelog lists avatar,
icon_button, dashed_border, action_row, inline_field as identical). One that takes a tone is a wrapper class, for
example `AvStatusChip(AvStatus s)` building `BondStatusChip(BondStatus(s.label, tone: s.tone.role, icon: s.icon))`.

## 3. Call-site changes
| Old | New | Find |
|---|---|---|
| `AvButtonVariant.black` (14) | `BondButtonVariant.strong` | `grep -rn "AvButtonVariant.black"` |
| `AvListRow(red: true)` | `BondListRow(urgent: true)` | `grep -rn "red: true"` |
| `AvSideNav(currentRoute:, onNavTap:)` (7) | `BondSideNav(selectedId:, onSelected:)` | `grep -rn "AvSideNav("` |
| `SideNavDestination(route:)` (32 uses), `SideNavGroup`, scroll key `side-nav-scroll` | `BondNavDestination(id:)`, `BondNavGroup`, `bond-side-nav-scroll` | `grep -rn SideNavDestination` |
| A `AvDateField(value:)` (21) | `BondDateField(value:, today: <app clock date>, onChanged:)`; `value` is nullable, `onCleared:` is new | `grep -rn AvDateField` |
| P `PtDateField(hasValue: false)` | `BondDateField(value: null, ...)`; P already passes `today` | `grep -rn "hasValue:"` |
| `AvSelect` dropdown variant | `BondSelectVariant.expanding` (inline list) | `grep -rn "AvSelect("` |
| `AvConfirm` string key on the armed action | `semanticsId`, giving `<id>-confirm`, `-cancel`, `-undo` | `grep -rn AvConfirm` |
| `AvCrewChip(...)` (8), `AvCrewColors.forCrew(n)` | `BondPersonChip`, `BondTokens.of(context).personColor(n)` | |

## 4. Data
None. Add the git dependency; keep the Figtree font in the UI package. Delete the two allowlist lines.

## 5. Acceptance
- `flutter analyze` and `flutter test` in the UI package, the screens package and each app.
- A test that each `AvTone.<x>.colors` (background, foreground, border) equals `avTokens.colorsFor(<x>.role)`; black is the exception.
- The app's `tool/ui_token_gate.sh` and `tool/no_popups_gate.sh`; then the web and phone walks.

## 6. Known gaps
- Dropped: black tone (4 `AvTone.black` uses: draw in ink locally), crew/customer/money/voice constants, l10n delegates, brand font, `intl`.
- `BondDateField` never reads the clock. `BondLabels` has no `==`: its scope notifies on every rebuild.
- `staleSince` is a prefix; A's `stale_since` takes the time as a parameter: keep a thin `AvStaleBanner`.
- `BondStartupFailed` is a whole `MaterialApp`. `Semantics(identifier)` is untested in a browser until the walk.
- S: its radii (6, 10, 16) become 8, 12, 16 under `BondRadius`; `ui/components/overlays/sbel_snackbar.dart` has no bond equivalent.

## 7. Added for the task widgets
- `BondMonthGrid` is exported with `dayBuilder` (a widget under each day number, hidden from screen readers), `daySemantics`
  (added to a cell's spoken label) and `firstWeekday` (default Sunday).
- `BondSearchPicker<T>`: removable picked chips, a search field and an inline result list with busy, empty and error
  lines. A stale answer is dropped. `BondPersonTile`: a person as a list row. New labels: `searching`, `searchFailed`, `remove`.
