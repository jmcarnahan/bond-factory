# Changelog

## 0.1.0 - unreleased

### Added (themable shape)
- `BondShape` (`r4, r8, r12, r16, r20`, plus `r4All` to `r20All`, `copyWith`, `lerp`, equality) and `BondTokens.shape` (default `const BondShape()`, same values as before). Every widget reads its corner radii from `BondTokens.of(context).shape`.
- `BondRadius.r4` to `r20` and `r4All` to `r20All` are `@Deprecated` aliases for one release. `BondRadius.pill` and `pillAll` stay (a pill is not a shape step).
- `BondPressable.borderRadius`, `BondPhoto.radius` and `BondDashedBorder.radius` are now nullable and default to the shape token (`r8`, `r12`, `r12`); passing a value works as before. `bondFocusedBorder` takes an optional `BondShape`.

### Added (task widgets support)
- `BondMonthGrid` is exported (moved to `primitives/bond_month_grid.dart`) with `dayBuilder` (a widget under each day number) and `firstWeekday` (default Sunday). `BondDateField` is unchanged.
- `BondMonthGrid.daySemantics`: text appended to a cell's spoken label (a `dayBuilder` marker is hidden from screen readers).
- `BondSearchPicker<T>`: removable picked chips, a search field and an inline result list with busy, empty and error lines; a stale answer is dropped.
- `BondPersonTile`: a person as a list row (avatar, name, subtitle, trailing).
- `BondLabels`: `searching`, `searchFailed`, `remove`.
- `BondTimeField` selects a box's text on focus, so typing replaces it.
- `BondTextField` with a `semanticsId` exposes its error message as its own node `<id>-error`, a live region
  so a screen reader announces it when it appears.

Tokens, theme, labels, semantics helper and the primitive widgets, lifted from the two near-identical app UI packages.

### Added
- Tokens: `BondTokens` (ThemeExtension for colours and font), `BondTone`, `BondToneRole`, `BondToneColors`, `BondSpace`, `BondRadius`, `BondShadows`, `BondText`, `BondLayout`, `BondSize`.
- Theme: `BondTheme.build(tokens, {brightness})`, `BondScope`.
- `BondLabels` and `BondLabelsScope` (English defaults, no intl); `bondSemantics`, `bondSemanticsOption`.
- Primitives: `BondActionRow`, `BondAvatar`, `BondBanner`, `BondButton`, `BondCard`, `BondChip`, `BondConfirm`, `BondDashedBorder`, `BondDateField`, `BondIconButton`, `BondInlineField`, `BondListRow`, `BondPhoto`, `BondPressable`, `BondSegmented`, `BondSelect`, `BondStatusChip`, `BondTextField` and `BondSearchField`, `BondTimeField`.

### Neutral vocabulary
- Colours moved from fixed app palettes into `BondTokens`; the red/black tones became `danger` and `ink`; `crew_colors` became `personPalette`.
- `BondToneRole? tone`: null means neutral. The wire name `red` still parses (to `danger`).
- `BondButtonVariant.black` is now `strong`; `BondListRow.red` is now `urgent`.

### Reconciliation (A = first app, P = second app)
- pressable: A wins on its own semantics node (container) and toggled state; P wins on an exposed-children mode. Both now take an explicit `semanticsId` instead of reading a string key.
- button: A wins on the nullable announced `selected`; P wins on drawing a selected button in the ink fill.
- icon_button, avatar, dashed_border, action_row, inline_field: identical in both; kept.
- card: P wins on the identifier wrapper with explicit child nodes.
- chip: P wins on the wrapping label and on speaking the count with the label.
- status_chip: P wins on the wrapping label and the identifier.
- photo: P wins on request `headers` for private images.
- banner: P wins on the single shared action widget; the large-text stacking rule is the same.
- list_row: A wins on `leadingWidth` and `done`; P wins on `titleMaxLines`; both kept.
- segmented: A wins on the wrap-whole-pills layout; P wins on per-option identifiers (`<id>-<value>`). The per-segment key was dropped.
- text_field: A wins on the soft counter, input formatters, alignment and focus colour; P wins on a wrapping hint (`hintMaxLines: 2`). P's hard character cap was dropped.
- select: A wins on the variants; the `dropdown` variant (a popup button) became `expanding`, an inline list that opens in the page flow. No popup allowlist entry is needed.
- confirm: A wins on `immediate` and `undoWindow`; P wins on stacking at large text and on dropping the dot when the line does not fit. New: `armTimeout` (default 10 s) disarms an armed confirm, and `semanticsId` identifies the confirm, cancel and undo buttons.
- date_field: P wins on `today` injected by the caller (the field never reads the device clock) and on the placeholder; its `hasValue` flag became a nullable `value`. New: `onCleared` and a Today button. `intl` was replaced by `BondLabels` month and weekday names.
- time_field: A only (the second app has none). Labels moved into `BondLabels`.

- date_field (dateTime mode): with no value, picking a day reports midnight and lights no time chip; the field stays open until a chip is tapped. Clear is offered in every mode when there is a value. With no value the grid follows a changed `today`.
- confirm: the "Sent . Undo" row is never stacked. The text-scale stacking threshold is the named constant `kStackTextScale` (1.25). The arm timeout sets the idle phase before calling `onCancel`, and a throwing `onCancel` is reported to the framework instead of leaving the widget armed.
- select: needs no popup allowlist entry. The plan expected up to 6 `DropdownButton` entries; the inline expanding list replaced the dropdown.

### Dropped or renamed
- confirm: the seed `confirmKey` (a key on the armed Confirm action) is dropped; use `semanticsId`, which gives `<id>-confirm`.
- side_nav: the scroll keys 'side-nav-scroll' and 'side-nav-whole-scroll' are now 'bond-side-nav-*'.
- side_nav: `SideNavDestination.route` became `id`.
- bottom_nav and side_nav badges: the colour moved from the seed's brand red to `danger.base`.

### Shell and components reconciliation
- side_nav: A wins on rail mode and the scrolling open account card. Groups fold inline, and the current place is a plain `selectedId`.
- bottom_nav: P wins on shrink-to-fit labels, a text-scale cap on the count pill, and the spoken real count.
- account_card: A wins on the in-place expanding layout, with generic name, subtitle and actions.
- person_chip: A wins on the dashed no-person chip. The dot colour is `personPalette[slot % length]`.
- deactivated: A wins on the `note` and `extra` slots.
- email_sign_in: A wins on the form structure. Validation is inline, and the page passes the result text.
- page_header: A wins on measuring the space given, not the screen. It gained a list of actions and breadcrumbs.
- stale_banner: P wins on the identifier node wrapping the banner. The caller formats the time.
- states: P wins on the live-region error message with an id.
- table: A wins on `rowTappable`. It gained a stacked phone layout below 540 wide.
- tabs: A wins. It gained a sideways scroll and an id per tab.
- logo_mark: neither wins. The app passes its own logo widget.
- message_preview: it now takes generic variants.
- timeline_list: A wins. The tone is a nullable `BondToneRole`.
- google_sign_in, startup_failed, rail_card, right_rail: re-typed from A with no behaviour change.

### Behaviour differences from the seeds
- `BondSegmented` cells now carry the tap on their semantics node, so assistive technology and test drivers can activate them.
- Dropped from the seeds: localisation delegates and scope (the app scope became `BondScope`, tokens only), the brand font and package, the crew/customer/money/voice layout constants, the black tone.
