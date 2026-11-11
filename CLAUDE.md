# bond-factory

Shared SDK monorepo for the bond app family (avalon-crm, sbel-crm, paga-time): small Dart/Flutter packages, Python libs and services. Nothing here ships except services/roof_measure, the one deployed service (private Docker image); demos are harnesses.

## Layout
- packages/  — Dart/Flutter packages (`bond_<x>` core, `bond_<x>_ui` widgets). Conventions + commands: packages/<pkg>/CLAUDE.md
- demos/     — Flutter harnesses, never shipped. Conventions + commands: demos/roof_demo/CLAUDE.md
- services/  — Python services. Conventions + commands: services/roof_measure/CLAUDE.md
- libs/      — Python libs (none yet)
- fixtures/  — cross-language contract fixtures (<= 100 KB each); see fixtures/README.md
- docs/      — contracts/, decisions/, research/; index docs/README.md
- make/      — root make includes (`make help` lists targets)
- tool/      — repo scripts (no_popups_gate.sh, changed_modules.sh)
- local/, tmp/ — LOCAL-ONLY (gitignored). Read specific files on demand; never read wholesale.
- .claude/   — settings.json + rules/ (committed); settings.local.json, worktrees/ (ignored)

## Validation policy — scoped during dev, full once pre-PR
- While working: stay in one module and run only its tests:
  `make -C packages/bond_roof test T=test/model_test.dart`
- Before a PR: `make changed` shows affected modules (reverse deps included);
  `make test-changed` runs them.
- Full `make test` runs ONCE per branch, pre-PR, never mid-task.
- `make analyze` and `make gates` are cheap; run freely.
- Tee long output to `tmp/` (e.g. `make test 2>&1 | tee tmp/test.log`).
- Override toolchains: `make FLUTTER=/path/to/flutter`.

## Hard rules
- No popups, dialogs or modal sheets. `make gates` enforces; allowlist tool/allowlist_popups.txt, max 6 entries.
- No code generation (no build_runner, freezed, json_serializable). Hand-write fromJson.
- Modules live at depth 2 exactly (`packages/<x>`, `demos/<x>`, `services/<x>`, `libs/<x>`); tests use `../../fixtures`.
- Modules depend on siblings only through pubspec `path:`.
- A `bond_<x>` core package imports no Flutter. Widgets go in `bond_<x>_ui`, backend adapters in `bond_<x>_<backend>`.
- Public API change: update the barrel and the module CHANGELOG.md in the same commit.
- Soft cap 300 lines per source file; split when next touched.
- Public repo: no personal emails, tokens, customer data, project ids, team ids, or real property addresses/coordinates in tracked files; real sites live in local/sites.json and local/test-data/. The public-hygiene hook (`.githooks/`, install once with `make hooks`) checks on commit and push; CI runs the same scan.
- Never read `services/*/tests/data/`, lockfiles, or `docs/research` images in full.

## Consuming from an app
- Depend by git: `git: {url: https://github.com/jmcarnahan/bond-factory.git, ref: <full 40-char sha>, path: packages/<pkg>}`.
- Tags are labels only. Pub rejects per-package tags mixed with sibling deps ("forbidden"), so pin the full SHA.
- Local dev: gitignored `pubspec_overrides.yaml` in the consumer. Remove it before committing the consumer's lock.

## Adding a module
- Copy the layout of packages/bond_roof (pubspec, analysis_options, lib/ + barrel, test/, CHANGELOG.md).
- Write a CLAUDE.md (<= 25 lines): role, key files, commands, rules.
- Add a Makefile with `test` and `analyze` targets (accepting `T=`).
- Register it in the root pubspec workspace (Dart) or uv members (Python).
- Add a row to tool/changed_modules.sh so `make changed` sees it.
