# Migrating the apps to bond-factory modules

One file per module says which app files it replaces, the adapter the app writes, the call-site changes, the data
changes, the acceptance commands and the behaviour the module dropped. These files name the three apps and their
real paths on purpose; nothing else in the repo does. Consuming syntax and pins: `docs/sdk/README.md`, `docs/sdk/sdk-pins.md`.
The policy behind it: `docs/decisions/2026-11-08-shared-modules-policy.md` (divergence happens only in the app's adapters).

## Legend

| Tag | App | Repo | Backend | Flutter |
|---|---|---|---|---|
| A | avalon-crm | `~/projects/avalon-crm` | `backend/avalon/` | `flutterui/packages/avalon_core` (`lib/src`), `avalon_ui`, `avalon_screens`, `apps/` |
| S | sbel-crm | `~/projects/sbel-crm` | `sbelcrm/` | phone `mobile/crm_proposals/lib`, web `flutterui/lib` |
| P | paga-time | `~/projects/paga-time` | `backend/pagatime/` | `flutterui/packages/pt_core` (`lib/src`), `pt_ui` |

Line counts and call-site counts were measured on 2026-11-08 with `wc -l` and `grep`; they include tests unless the row says
otherwise. Re-run the grep given in each file's section 3 before you start; the numbers will have moved.

Per-app notes live beside the module notes (`sbel.md`).

## Index

| Module | File | Adopters, in the order the research recommends |
|---|---|---|
| `bond_json` | `bond_json.md` | A, P, S (new code) |
| `bond_test_support` | `bond_test_support.md` | A, P, S |
| `bond_api` | `bond_api.md` | A, P, S phone; S web later |
| `bond_ui` | `bond_ui.md` | A, P; S phone after a token map; S web last |
| `bond_service_kit` | `bond_service_kit.md` | A, P; S in part |
| `bond_storage` | `bond_storage.md` | A, P, S |
| `bond_auth_py` | `bond_auth_py.md` | A, P; S after its contract migration |
| `bond_jobs` | `bond_jobs.md` | A, P |
| `bond_auth`, `bond_auth_firebase` | `bond_auth.md`, `bond_auth_firebase.md` | A, P; S `bond_auth` after its contract migration, `bond_auth_firebase` for break-glass only, kept |
| `bond_sync`, `bond_sync_powersync`, `bond_sync_py` | `bond_sync.md`, `bond_sync_powersync.md`, `bond_sync_py.md` | S first, then A |
| `bond_oauth` | `bond_oauth.md` | A, S |
| `bond_calendar` | `bond_calendar.md` | S (Microsoft Graph), A (Google read); P adopts nothing |
| `bond_tasks_py` | `bond_tasks_py.md` | S, A |
| `bond_tasks`, `bond_tasks_ui` | `bond_tasks.md` | S web, S phone, A |
| `bond_connections`, `bond_connections_ui` | `bond_connections.md` | A, S |
| `bond_signin`, `bond_signin_ui` (Dart) and `libs/bond_signin` | `bond_signin.md`, `bond_signin-cutover.md` | S, A, P, after `bond_auth(_py)`, `bond_oauth`, `bond_connections` |

## Dart and Python pairs

A wire contract has a client half and a server half. Migrate both halves of a pair in the same app, in the same SHA bump.

| Dart (client) | Python (server) |
|---|---|
| `bond_auth`, `bond_auth_firebase` | `bond_auth_py` |
| `bond_sync`, `bond_sync_powersync` | `bond_sync_py` |
| `bond_tasks`, `bond_tasks_ui` | `bond_tasks_py`, with `bond_calendar` for the mirror |
| `bond_connections`, `bond_connections_ui` | `bond_oauth` |
| `bond_signin`, `bond_signin_ui`, `bond_auth` (sessions) | `libs/bond_signin`, `bond_oauth`, `bond_auth_py` (sessions) |
| `bond_api` | `bond_service_kit` (the error body) |

## Suggested order

Each module lands on its own, so stop after any step. The order is per module and per app: sync comes first only for S,
whose core already has the shape the lib took, and last for A and P. The order keeps later steps small:

1. `bond_json`, `bond_test_support` (pure moves behind re-exports).
2. `bond_api`, then `bond_auth` and `bond_auth_firebase` (they use its hooks).
3. `bond_service_kit`, then `bond_storage`, `bond_jobs`, `bond_auth_py` (they use its error body and clock).
4. `bond_ui` once the token adapter is written.
5. Sync and OAuth last; both need decisions of the owning app.
6. Direct sign-in (`bond_signin.md`) AFTER `bond_auth`/`bond_auth_py`, `bond_oauth` and `bond_connections` are adopted, in the same SHA bump as their 0.2.0 versions.
   It replaces Firebase sign-in and keeps Firebase only as the break-glass route (S: `bond_auth_firebase`, break-glass only) and for push (A, P). All SDK work lands before any app migrates
   to it, so an app takes one step per module. Order inside it: S (single tenant, full scopes at sign-in, its phone is the
   main surface), then A (identity-only sign-in plus role asks), then P (identity only). Each app's first LIVE provider run
   is part of its acceptance (`bond_signin.md` section 6); nothing in the SDK has run against a live provider yet.

P is the cheapest first adopter for anything that touches the backend (2 Alembic revision files against 24 in A and 83 in S, head 082).

## Common procedure, per module

1. Branch in the app. Make sure `pubspec_overrides.yaml` is in `.gitignore` and `.dockerignore`.
2. Add the dependency at one full 40-character SHA, the same SHA for every bond module (Dart: git + `path:`;
   Python: Poetry `git` + `rev` + `subdirectory`). Run `flutter pub get` or `poetry lock`.
3. Write the adapter from section 2 of the module file. Keep the old file names and public names, so call sites compile unchanged.
4. Run the app's existing tests against the adapter. Where behaviour drifted, section 6 lists the cases; record any fix as an adapter, not a patch.
5. Delete the local copy the adapter replaced. Keep the adapter.
6. Update `docs/sdk/sdk-pins.md` in the app (module, SHA, date, local patches).
7. Run the acceptance commands of section 5. Run the app's full suite once, before the PR, not between steps.

## Acceptance commands, per app

| Check | Dart (A, P, S) | Python (A, P) |
|---|---|---|
| Resolve | `flutter pub get` in the workspace root | `poetry lock`, `poetry install` |
| Static | `flutter analyze` | `ruff check` |
| Tests | `flutter test` per edited package | `pytest` on the touched files, then the suite |
| Tables | | `schema_contract(Base.metadata, tables=[...]).assert_matches(engine)` from `bond_service_kit`, plus the app's own `alembic upgrade head` then `alembic revision --autogenerate` showing an empty diff |
| Gates | the app's own no-popups and token gates | |

## What a module file does not cover

- The migration of A's `AvalonApi`-style service layers, routers and screens: only what the module replaces.
- Product decisions (which capability names, which sync tables): the app decides and writes them in its adapter.
- Anything in `local/`: research and plans stay out of the public repo.
