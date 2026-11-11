# bond-factory

Monorepo of Flutter/Dart components shared by John's apps (avalon-crm, paga-time, sbel-crm),
plus the small services some of them need.

## Layout

- `packages/bond_roof` pure Dart: roof model JSON, totals, diagram scenes, SVG and PDF export.
- `packages/bond_roof_ui` Flutter: widgets that draw a scene, print and share.
  Both packages live in one pub workspace (root `pubspec.yaml`).
- `demos/` demo apps that exercise the packages end to end. Not shipped.
- `services/` services that back a package when the work cannot run on the device
  (today: `services/roof_measure`, Python, turns an address into a roof model). One uv workspace
  (root `pyproject.toml`, `uv.lock`).
- `fixtures/` JSON fixtures shared by the service tests and the Dart contract tests.
- `docs/contracts/` wire contracts (start with `docs/contracts/roof_model.md`).
- `docs/decisions/` decision records (start with `docs/decisions/2026-11-07-roof-poc-summary.md`).
- `docs/research/` per-topic research notes and evidence behind the decisions.
- `make/` make fragments included by the root `Makefile`. Run `make help`.
- `tool/` the no-popups gate, its allowlist and `changed_modules.sh`.
- `local/` gitignored scratch space.

## Quick start

Requires Flutter 3.41 (Dart 3.11), Python 3.12 and [uv](https://docs.astral.sh/uv/).
Root make targets use `flutter` from your PATH; override with `make FLUTTER=/path/to/flutter ...`.

```
make setup-service  # create the service virtualenv
make test           # test-dart + test-flutter + test-service
make analyze        # dart analyze / flutter analyze
make gates          # no-popups gate
make demo-web       # run the demo in Chrome
make build-web      # release web build in demos/roof_demo/build/web
make changed        # modules affected by changes vs main (BASE=<ref> to change)
cd services/roof_measure && make measure ADDR="100 Example Ave, Sampletown, CA 90000"
```

Real test sites are configured in `local/sites.json` (untracked); copy `services/roof_measure/tests/sites.example.json`.

Consumers pin a full 40-char commit SHA in `git:` refs (per-package tags cannot be mixed with sibling deps).

## Components

Apps consume these modules as described in `docs/sdk/README.md`.

| Component | Kind | Status |
|---|---|---|
| `packages/bond_roof` | pure Dart: roof model JSON, totals, diagram scenes, SVG and PDF export | 0.2.0 |
| `packages/bond_roof_ui` | Flutter: widgets that draw a scene, print and share | 0.2.0 |
| `services/roof_measure` | Python: address -> footprint + LiDAR (+ Solar) -> roof model JSON; also importable as a library | 0.2.0 |
| `demos/roof_demo` | Flutter: type an address, see the three diagrams, print | POC |

## House rules

Same as avalon-crm: no popups, dialogs or modal sheets of any kind (`tool/no_popups_gate.sh`);
no code generation (no build_runner, freezed, json_serializable); hand-written `fromJson`;
`flutter_lints` plus the six extra rules in `analysis_options.yaml`; tests per package.

## Licensing

The repository and the roof pipeline (`services/roof_measure`, because it links compas_cgal and a GPL component of CGAL) are licensed under GPL-3.0-or-later (see `LICENSE` and `NOTICE`). `packages/bond_roof` and `packages/bond_roof_ui` are MIT (their own `LICENSE` files). The Roboto font in `packages/bond_roof_ui/assets/fonts/` keeps its own Apache-2.0 licence. Pinning `bond_roof` or `bond_roof_ui` by git brings MIT code into an app. Importing `roof_measure` as a Python library brings GPL-3.0-or-later code into that backend. Nothing here is a claim that it is legally sufficient for any particular use.
