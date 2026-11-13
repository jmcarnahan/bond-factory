# bond-factory

Monorepo of Flutter/Dart components shared by John's apps (avalon-crm, paga-time, sbel-crm),
plus the small services some of them need.

## Layout

- `packages/` Dart and Flutter packages (`bond_<x>` pure Dart core, `bond_<x>_ui` widgets, adapters per backend). One pub workspace (root `pubspec.yaml`).
- `libs/` Python libraries the services import (SQLAlchemy mixins, Protocol seams, no migrations). One uv workspace (root `pyproject.toml`, `uv.lock`).
- `services/` Python services: `roof_measure` (the one deployed service) and `sdk_example` (a reference app, never shipped); `services/legacy_host` is a test-only "existing app" host.
- `demos/` Flutter harnesses that exercise the packages end to end. Not shipped.
- `fixtures/` JSON fixtures shared by the Python and Dart tests.
- `docs/` `contracts/` (wire contracts), `decisions/`, `migration/` (one note per module), `sdk/`, `test/` (walk recipes), `research/`. Index: `docs/README.md`.
- `make/` make fragments included by the root `Makefile`. Run `make help`.
- `tool/` the repo gates and scripts (`no_popups_gate.sh`, `changed_modules.sh`, ...).
- `local/` gitignored scratch space.

## Quick start

Requires Flutter 3.41 (Dart 3.11), Python 3.12 and [uv](https://docs.astral.sh/uv/).
Root make targets use `flutter` from your PATH; override with `make FLUTTER=/path/to/flutter ...`.

```
make setup-service  # create the service virtualenv (Python library use: docs/contract-0.2.md section 3)
make test           # test-dart + test-flutter + test-service + test-libs + test-example + test-legacy-host + test-adopter-lane
make analyze        # dart analyze / flutter analyze
make gates          # popups, ui tokens, boundaries, line cap, public hygiene
make demo-web       # run the demo in Chrome
make build-web      # release web build in demos/roof_demo/build/web
make adopter-check APP=<checkout>  # an adopting app's own battery against this tree (docs/sdk/adopter-check.md)
make changed        # modules affected by changes vs main (BASE=<ref> to change)
cd services/roof_measure && make measure ADDR="100 Example Ave, Sampletown, CA 90000"
```

Real test sites are configured in `local/sites.json` (untracked); copy `services/roof_measure/tests/sites.example.json`.

Consumers pin a full 40-char commit SHA in `git:` refs (per-package tags cannot be mixed with sibling deps).

## Components

How an app consumes them: `docs/sdk/README.md`. The daily TODO checklist (due times, three-stage notices, inbox, push,
capture, phone alerts) is adopted in the order of `docs/migration/todo-checklist.md`. One migration note per module is in `docs/migration/`.

| Component | Kind | Role |
|---|---|---|
| `packages/bond_json` | pure Dart | null-safe JSON readers and UTC timestamp helpers |
| `packages/bond_api` | pure Dart | HTTP `ApiClient`, typed errors, error-body parser, SSE |
| `packages/bond_auth` | pure Dart | auth contracts: token stores, session, capability policy, gateways |
| `packages/bond_auth_firebase` | Flutter | Firebase adapter for `bond_auth` |
| `packages/bond_signin`, `bond_signin_ui` | pure Dart, Flutter | direct sign-in client; sign-in screen and system-browser port |
| `packages/bond_connections`, `bond_connections_ui` | pure Dart, Flutter | OAuth connection status; card, list and return banner |
| `packages/bond_sync`, `bond_sync_powersync` | pure Dart, Flutter | backend-agnostic sync core; PowerSync connector, store and opener |
| `packages/bond_ui` | Flutter | design tokens, theme, labels and widgets |
| `packages/bond_test_support` | Flutter | shared widget-test helpers |
| `packages/bond_tasks`, `bond_tasks_ui` | pure Dart, Flutter | task model, REST client, controller, stage helpers; task widgets |
| `packages/bond_notify`, `bond_notify_ui` | pure Dart, Flutter | inbox notices, feed and controller; inbox widgets |
| `packages/bond_push` | Flutter | Apple push token, device registration and taps (iOS only) |
| `packages/bond_tasks_notifications` | Flutter | local task alerts, action handler and the alerts coordinator |
| `packages/bond_tasks_powersync`, `bond_notify_powersync` | Flutter | task repository and notice feed over the synced store |
| `packages/bond_roof`, `bond_roof_ui` | pure Dart, Flutter | roof model, totals, diagrams, SVG and PDF export; widgets that draw and print them |
| `libs/bond_service_kit` | Python | FastAPI and SQLAlchemy plumbing: errors, middleware, rate limit, clock, health |
| `libs/bond_auth_py`, `bond_signin`, `bond_oauth` | Python | token verification and sessions; direct sign-in; OAuth flows and encrypted token storage |
| `libs/bond_jobs`, `bond_storage`, `bond_sync_py` | Python | job queue and worker; S3-compatible storage; server side of device sync |
| `libs/bond_calendar` | Python | Microsoft Graph and Google calendar providers behind one protocol |
| `libs/bond_tasks_py` | Python | tasks table, due instants, notice stages, sweep, outbox, calendar mirror |
| `libs/bond_notify_py`, `bond_push_py`, `bond_capture_py` | Python | stored inbox; Apple push delivery; natural-language capture |
| `services/roof_measure` | Python | address -> footprint + LiDAR (+ Solar) -> roof model JSON; also importable as a library (GPL-3.0-or-later) |
| `services/sdk_example` | Python | reference FastAPI app wiring every bond Python lib; never shipped |
| `services/legacy_host` | Python | test-only "existing app" host: legacy columns, wire and clients; never shipped |
| `demos/roof_demo`, `demos/sdk_demo` | Flutter | roof demo; web and iOS harness for every SDK package. Not shipped |

## House rules

Same as avalon-crm: no popups, dialogs or modal sheets of any kind (`tool/no_popups_gate.sh`);
no code generation (no build_runner, freezed, json_serializable); hand-written `fromJson`;
`flutter_lints` plus the six extra rules in `analysis_options.yaml`; tests per package.

## Licensing

The repository is licensed under the MIT License (see `LICENSE` and `NOTICE`). The one exception is `services/roof_measure`, which stays GPL-3.0-or-later (its own `LICENSE`) because it links compas_cgal, which pulls in a GPL component of CGAL; an app that imports that service as a library takes on GPL for that backend, and nothing else in the repo imports it. Third-party files keep their notices: the polylabel port in `packages/bond_roof` (ISC) and the Roboto font in `packages/bond_roof_ui/assets/fonts/` (Apache-2.0). Nothing here is legal advice. Record: `docs/decisions/2026-11-11-licence-mit.md`.
