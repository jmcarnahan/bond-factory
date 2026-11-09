# 2026-11-08 Shared SDK architecture (D1 to D14, condensed)

Status: accepted. Dated, append-only. The full plan lives outside the repo; these are the decisions it rests on.

## Decisions

- **D1 Scope.** Tier 1 and Tier 2 shared modules plus connections, calendar and tasks. LLM, push, platform,
  team admin and l10n stay out.
- **D2 Tasks.** The SDK owns tasks (table, status, checklist, reminders). Google Calendar and Microsoft Graph
  are mirrors behind one `CalendarProvider` protocol. Reminders fire from our job queue, never the provider.
- **D3 Tokens.** Colours and fonts live in a `BondTokens` theme extension. Spacing, radius and text scale are
  plain constants (`BondSpace`, `BondRadius`, `BondText`). Alias tricks belong in app migrations, not packages.
- **D4 Auth contract.** `sub` is the user id, the `capabilities` claim, `/auth/refresh`, and revocation by
  `sessions_valid_after`, with an `extra_claims` dict argument on `create_access_token`. Capability vocabularies stay per app.
- **D5 Firebase config.** Clients read it at runtime from `GET /auth/providers`. No `firebase_options.dart`.
- **D6 Sync.** `bond_sync` is pure Dart with a store seam. `bond_sync_powersync` is the adapter.
- **D7 Error body.** `{"detail": {"code", "message", "hint"?}}`. `bond_api` also parses the legacy string form.
- **D8 Delivery.** Real CI (analyze, gates, tests, hygiene, wheels). Dart by git SHA, Python by Poetry git
  `rev` or the CI wheel.
- **D9 Policy.** Pinned SHA, divergence only in adapters. No riverpod, intl, localizations or go_router in
  shared packages. See `2026-11-08-shared-modules-policy.md`.
- **D10 Consumers.** Every Dart package resolves in a single-package consumer and pins no `intl`.
- **D11 Libraries.** Libs never own migrations: SQLAlchemy mixins plus `schema_contract()`. Service functions
  take a session (`bond_jobs` queue functions take an engine). No lib imports another lib; seams are `Protocol`s.
- **D12 Examples.** `demos/sdk_demo` and `services/sdk_example` wire every module with fake providers and are
  the reference for migrations.
- **D13 Docs.** Each module has a README (at most 120 lines) and a per-app migration note (at most 100 lines).
- **D14 Scaffold first.** All modules are scaffolded and registered once, so parallel builders never edit a
  registry file.

## Module list

Dart core: `bond_json`, `bond_api`, `bond_auth`, `bond_sync`, `bond_tasks`, `bond_connections`, `bond_roof`.
Flutter: `bond_test_support`, `bond_ui`, `bond_auth_firebase`, `bond_sync_powersync`, `bond_tasks_ui`,
`bond_connections_ui`, `bond_roof_ui`.
Python libs: `bond_service_kit`, `bond_storage`, `bond_auth_py`, `bond_jobs`, `bond_sync_py`, `bond_oauth`,
`bond_calendar`, `bond_tasks_py`.
Examples: `demos/sdk_demo`, `services/sdk_example`.
