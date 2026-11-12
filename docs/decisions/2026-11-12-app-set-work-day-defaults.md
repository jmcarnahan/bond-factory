# 2026-11-12 The app sets the default work day

Status: accepted. Dated, append-only. Extends `2026-11-11-due-instant.md`.

## Context

The start of day, the end of day and the lead time had fixed defaults (08:00, 17:00, 60 minutes) written into the
`task_user_settings` table. A person with no row got the same constants. An app whose organisation works another day
could not change the default, and a settings screen could not tell a default from a choice.

## Decisions

- **W1** The app passes its default as one `UserPrefs` (`defaults=` of `get_settings`, `update_settings` and
  `StoredPreferences`). `None` keeps the old constants. The app builds ONE `StoredPreferences` and passes it everywhere
  preferences are read.
- **W2** In `task_user_settings`, `start_of_day`, `end_of_day` and `lead_minutes` are nullable and have no column
  default, as `time_zone` already was. NULL means "follow the app default". A stored value is the person's own choice.
  The host adds a revision that drops NOT NULL (the example's is `0006`).
- **W3** `GET` and `PUT /tasks/settings` answer the effective values plus `"overridden": [names]`, the fields the
  person has stored, in the order `time_zone`, `start_of_day`, `end_of_day`, `lead_minutes`.
- **W4** In a `PUT`, a field that is present and `null` resets it to the default (NULL is stored). An absent field is
  unchanged. The effective work day is what is checked and compared, so a reset that changes the end of day or the zone
  recomputes due instants.
- **W5** Dart: `TaskSettings.overridden`, `TaskSettingsPatch(reset: {...})`, and one inline "Reset to default" control
  per field in `BondTaskSettingsForm`. No popup.

## Consequences

- Rows written before this change hold all three values and would read as overridden forever. The host revision sets to
  NULL every stored value equal to the old constants (08:00, 17:00, 60); the example's `0006` does. A person who chose
  exactly a constant loses nothing: the default is the same until the app changes it.
- A reset can be refused with `invalid_work_day` when the default equals the other stored bound. Reset both together.
- The example reads the default from `SDK_EXAMPLE_START_OF_DAY`, `SDK_EXAMPLE_END_OF_DAY` and `SDK_EXAMPLE_LEAD_MINUTES`.
  Its default zone stays unset, so the `time_zone_unknown` warning still fires for a person with no stored zone.
