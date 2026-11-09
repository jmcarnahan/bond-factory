# Consuming bond-factory from an app

bond-factory is a public monorepo of small shared modules. An app depends on a module by git and a pinned
commit. Nothing here is published to pub.dev or PyPI. Divergence between apps happens only in each app's own
adapters (see `docs/decisions/2026-11-08-shared-modules-policy.md`).

## Dart and Flutter (git + full SHA + `path:`)

Toolchain: 3.47.8 (this branch and CI); the packages' floor is Flutter 3.41 and Dart ^3.11.

```yaml
dependencies:
  bond_api:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: 0123456789abcdef0123456789abcdef01234567   # full 40-char SHA
      path: packages/bond_api
  bond_ui:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: 0123456789abcdef0123456789abcdef01234567   # same SHA
      path: packages/bond_ui
```

- **Pin the full 40-character SHA.** Tags are labels only. Pub rejects a per-package tag when sibling packages
  are reached through `path:` deps ("forbidden"), and every package that depends on a sibling does.
- **One git dependency per package the app imports.** Sibling dependencies (for example `bond_api` needing
  `bond_json`) resolve from the same SHA automatically. Use the same SHA for every entry.
- Packages never pin `intl`, `flutter_localizations`, `flutter_riverpod` or `go_router`. Strings enter shared
  widgets through a `*Labels` object with English defaults, and routing and providers stay in the app.
- `tool/consumer_check.sh` (`make consumer-check`) proves each package resolves outside the workspace.
- Toolchain: this branch and CI use Flutter 3.47.8 / Dart 3.13.7; the packages' floor is Flutter 3.41 and Dart >= 3.11 (`sdk: ^3.11.0`).
  Apps still on Flutter 3.47.2 should bump when they adopt a module.

### Local development against a checkout

Create a gitignored `pubspec_overrides.yaml` next to the app's `pubspec.yaml`:

```yaml
dependency_overrides:
  bond_api:
    path: ../bond-factory/packages/bond_api
  bond_json:
    path: ../bond-factory/packages/bond_json
```

Override every bond package that resolves (siblings included). In a workspace, put the same
`dependency_overrides` block in the workspace root `pubspec.yaml` instead, since members cannot carry
overrides. Delete the override and re-run `flutter pub get` before committing the app's lockfile.

Add to the app's `.gitignore` and `.dockerignore`:

```
pubspec_overrides.yaml
```

## Python (Poetry git dependency or CI wheel)

```toml
[tool.poetry.dependencies]
python = ">=3.12,<3.14"   # bond_storage requires it; "^3.12" fails `poetry lock`
bond_storage = { git = "https://github.com/jmcarnahan/bond-factory.git", rev = "<sha>", subdirectory = "libs/bond_storage" }
```

- The python image stage needs git: `apt-get update && apt-get install -y --no-install-recommends git`.
- Alternative: every CI run builds one wheel per lib; tagged runs (`v*`) attach them to the GitHub Release.
  Depend on the wheel URL when the image cannot install git.
- Local development: `poetry add --editable ../bond-factory/libs/bond_storage`. Revert it before committing
  `pyproject.toml` and `poetry.lock`.
- Libs never import each other (Poetry cannot resolve uv workspace sources). Cross-lib seams are `Protocol`s
  the app wires, as `services/sdk_example` does.
- Libs never own migrations. They ship SQLAlchemy mixins and a `schema_contract()` the app tests against its
  own engine; the app writes its own Alembic revisions.

## Versioning and upgrades

- A git ref or `rev` pins the COMMITTED state of bond-factory, not the working tree. Land docs and code in one
  commit before an app pins it, and read the docs at the pinned SHA.

- Each module is SemVer-versioned in its own `pubspec.yaml` or `pyproject.toml` and keeps a `CHANGELOG.md`.
  A public API change updates the barrel and the changelog in the same commit.
- Each app keeps `docs/sdk/sdk-pins.md` (template: `docs/sdk/sdk-pins.md` here): module, SHA, date, local patches.
- Upgrade procedure:
  1. Read the module changelogs between the old and new SHA.
  2. Change every Dart ref and Python rev to the new SHA in one commit.
  3. `flutter pub get` or `poetry lock`, then run the app's tests and gates.
  4. Update the pins file. Local patches are temporary: send them upstream, then delete them.

## Module index

| Module | Layer | Phase | What it is |
|---|---|---|---|
| `bond_roof` | pure Dart | 0 | Roof model, geometry and the wire contract |
| `bond_roof_ui` | Flutter | 0 | Roof diagram widgets |
| `bond_json` | pure Dart | 1 | Safe JSON and date parsing helpers |
| `bond_api` | pure Dart | 1 | HTTP client, typed errors, auth hooks, SSE |
| `bond_test_support` | Flutter | 1 | Test host and fakes for widget tests |
| `bond_ui` | Flutter | 1 | Tokens, widgets and the walkable-semantics convention |
| `bond_service_kit` | Python | 1 | FastAPI plumbing, error body, rate limit, health, clock |
| `bond_storage` | Python | 1 | Object storage with per-company keys |
| `bond_auth_py` | Python | 1 | Firebase id-token exchange, session JWT, revocation |
| `bond_jobs` | Python | 1 | Job queue and worker with an injected clock |
| `bond_auth` | pure Dart | 2 | Auth gateway, token store, session refresh |
| `bond_auth_firebase` | Flutter | 2 | Firebase id-token source and federated sign-in |
| `bond_sync` | pure Dart | 2 | Sync core with a store seam |
| `bond_sync_powersync` | Flutter | 2 | PowerSync adapter for `bond_sync` |
| `bond_sync_py` | Python | 2 | Server side of sync upload |
| `bond_oauth` | Python | 2 | OAuth flows with encrypted token storage |
| `bond_calendar` | Python | 3 | Calendar provider protocol, Google and Microsoft mirrors |
| `bond_tasks_py` | Python | 3 | Tasks, checklists and reminders |
| `bond_tasks` | pure Dart | 3 | Task models and client |
| `bond_tasks_ui` | Flutter | 3 | Task screens |
| `bond_connections` | pure Dart | 3 | Connection status models and client |
| `bond_connections_ui` | Flutter | 3 | Connection status screens |

`demos/sdk_demo` (Flutter web, :8078) and `services/sdk_example` (FastAPI, :8012) exercise every module in
fake mode and are the reference for wiring. The walk recipe is `docs/test/WEB.md`.
