# adopter-check: run an app's own battery against this tree

`make adopter-check APP=<path to the app checkout>` runs the adopting app's regression suites with its bond-factory
dependencies pointed at THIS working tree, so a change to a module is tested by the app that pins it before it merges.
It is opt-in and local: apps are separate repositories and CI here never sees them. Why:
`docs/decisions/2026-11-12-adopter-proof.md`.

Options: `CONFIG=<file>` reads the adopter file from that path instead of `<APP>/.bond-adopter.toml`, so the lane can be tried
against an app that has not added its file yet; `SUITE=<name>` runs one suite; `KEEP=1` keeps the temp copy and prints its path. Directly:
`python3 tool/adopter_check.py --app <path> --bond <this checkout> [--config FILE] [--suite NAME] [--keep] [--list]` (`--list` prints the
parsed plan and runs nothing).

## Adopters

Run the lane for every adopter that pins a module the change touches, before the PR merges. Pass each app's checkout as `APP=`. S and A are the two adopting apps, named as in `docs/migration/README.md`.

| App | Adopter file | Suites |
|---|---|---|
| S | `.bond-adopter.toml` (present) | overlay-took, backend, web, phone |
| A | planned (draft in its migration notes) | until the file lands, run its own tests by hand after re-pinning |

## `.bond-adopter.toml`

The app owns this file, at its root. Version 1:

```toml
version = 1

[copy]
extra = [".env.test"]

[[python]]
dir = "."
setup = ["poetry install --no-interaction"]
overlay = "poetry run python -m pip install --no-deps -e {lib}"
libs = ["bond_service_kit", "bond_sync_py"]

[[flutter]]
dir = "app"
packages = ["bond_api", "bond_tasks"]
setup = ["flutter pub get"]

[[suite]]
name = "backend"
dir = "."
run = "poetry run pytest tests/test_characterization.py -q"
env = { TZ = "America/Los_Angeles" }
timeout = 1800
```

| Key | Meaning |
|---|---|
| `version` | must be `1` |
| `[copy].extra` | optional; ignored FILES the suites need (paths relative to the app root), copied as well. A directory entry is skipped, so list its files |
| `[[python]]` | zero or more Python projects. `dir` is the project directory; `setup` commands run in the copy, in order; `overlay` runs once per entry of `libs`; `libs` are names under `<bond>/libs` |
| `[[flutter]]` | zero or more Dart or Flutter projects. `dir` is the project directory; `packages` are names under `<bond>/packages` (list the packages you depend on directly: their bond siblings, found through `path: ../<sibling>` in each pubspec, are overridden too), written to `<dir>/pubspec_overrides.yaml` as path overrides, closure included; `setup` runs after that |
| `[[suite]]` | one or more. `name` (letters, digits, `_.-`), `dir` (cwd inside the copy), `run` (a shell command), optional `env` (merged over the current environment) and `timeout` (seconds, default 1800) |

Placeholders in `setup`, `overlay` and `run`: `{bond}` (absolute path of this checkout), `{lib}` (overlay only: the
absolute path of the lib being overlaid), `{copy}` (the temp copy root). Each is shell-quoted when substituted
(`shlex.quote`), so write `{bond}` bare, never inside your own quotes: `sh -c 'echo "$0"' {bond}`, not `sh -c 'echo {bond}'`. Every `dir` and `extra` path must be relative
and stay inside the app (no leading `/`, no `..`).

## What the lane does

1. Validates: the app exists; the file parses; `version == 1`; every named lib and package exists in this checkout;
   every path stays inside the app; there is at least one suite; no `pubspec_overrides.yaml` would be copied for a
   Flutter project (it must not be tracked). A validation error prints one line and exits 2.
2. Copies the app to a temp dir. For a git checkout the file list is `git ls-files --cached --others --exclude-standard`
   (tracked plus untracked-not-ignored, so uncommitted work is tested) plus `[copy].extra`; files git lists but that
   are missing on disk are skipped. For any other directory it copies everything except `.git`, `.venv`, `.dart_tool`,
   `build` and `node_modules` at the app root, and `.dart_tool` and `build` inside each project `dir`. Layout and file modes are kept. The app checkout is only read: the one command run
   against it is read-only `git`, no worktree is added, and every later command runs with its cwd inside the copy
   (`GIT_CEILING_DIRECTORIES` is set so git cannot find a repository above it).
3. Points the dependencies at this checkout: writes `pubspec_overrides.yaml` for each Flutter project and runs its
   `setup`; runs each Python project's `setup`, then `overlay` once per lib. A failed setup or overlay is a row named
   `setup:<dir>` and the suites under that directory are SKIPPED.
4. Runs each suite (or the one named by `--suite`) with `/bin/sh -c`, cwd `<copy>/<dir>`, output in
   `<copy>/.adopter-logs/<name>.log` (the last 30 lines print on failure). At the timeout the whole process group is
   killed and the row is TIMEOUT.
5. Prints a table (suite, PASS / FAIL / TIMEOUT / SKIPPED, seconds, log path) and a summary line with the bond commit and
   the app commit (`git rev-parse --short HEAD`, plus ` (dirty)` when the tree has uncommitted changes).
6. Removes the temp copy, also on Ctrl-C, unless `--keep`.

Exit codes: 0 every row PASS; 1 any FAIL, TIMEOUT or SKIPPED; 2 a validation error.

## Example: a Poetry backend and two Flutter projects

```toml
version = 1

[[python]]
dir = "backend"
setup = ["poetry install --no-interaction"]
overlay = "poetry run python -m pip install --no-deps -e {lib}"
libs = ["bond_service_kit", "bond_storage", "bond_tasks_py"]

[[flutter]]
dir = "mobile"
packages = ["bond_api", "bond_tasks"]
setup = ["flutter pub get"]

[[flutter]]
dir = "web"
packages = ["bond_api", "bond_ui"]
setup = ["flutter pub get"]

[[suite]]
name = "backend"
dir = "backend"
run = "poetry run pytest -q"
env = { TZ = "America/Los_Angeles" }

[[suite]]
name = "mobile"
dir = "mobile"
run = "flutter test"

[[suite]]
name = "web"
dir = "web"
run = "flutter test"
```

## Notes

- The tool needs Python 3.11+ (`tomllib`); on an older python it prints one line and exits 2. `make setup-py` creates `.venv`.
- Isolation: a file whose parent path is a symlink leading outside the copy is not copied, and a project or suite `dir`
  that resolves outside the copy exits 2. Background processes a command leaves behind are killed when it ends, and
  SIGTERM or SIGHUP stops the running suite and removes the copy.
- `pubspec_overrides.yaml` holds double-quoted absolute paths.
- The copy has no `.git`, so a suite that shells out to git sees no repository.
- Confirm the overlay took: add a suite that prints a lib's `__file__` and checks it is under `{bond}`, passed as an
  argument (the tool shell-quotes it, so never wrap it in your own quotes):
  `run = '''poetry run python -c 'import sys, bond_service_kit as m; assert m.__file__.startswith(sys.argv[1]), m.__file__' {bond}'''`.
- Setup and overlay steps have a fixed 1800 second cap each; only suites take `timeout`.
- The copy has no virtualenv, so `setup` must create one (for example `poetry install`).
- Suites that read fixtures by relative path keep working because the layout is kept.
- Set `TZ` in a suite's `env` when the app's tests need a fixed zone.
- A Python lib or service that lives outside `libs/` (for example `services/roof_measure`) is not an `overlay` entry:
  install it with a `setup` command that names `{bond}` (for example `poetry run python -m pip install --no-deps -e {bond}/services/roof_measure`).
- When the app's Flutter projects form a pub workspace, point the `[[flutter]]` `dir` at the workspace root: pub writes
  and reads `pubspec_overrides.yaml` there, not in a member package.
- Self-test of the lane itself, against a stub app that needs no Poetry or Flutter: `make test-adopter-lane`
  (and `make adopter-check APP=tool/adopter_stub` to see a run).
