# 2026-11-11 Licence: MIT for the repository, GPL kept for the roof service

Status: accepted. Dated, append-only. Supersedes the licence section of `2026-11-10-roof-module-v1.md`.
This is not legal advice.

## Context

The repository carried GPL-3.0-or-later as one licence because the roof measurement service links a GPL
component (the CGAL straight-skeleton package, through `compas_cgal`). The apps pin the shared packages by
commit and ship through the App Store, where GPL-3.0 is widely held to conflict with the distribution terms.

## Decisions

- **M1** The repository is MIT: root `LICENSE`, "Copyright (c) 2026 John Carnahan". The owner is the sole
  author of every commit (two git author names, one person) and so can relicense.
- **M2** `services/roof_measure` stays GPL-3.0-or-later with its own `LICENSE` file, because it links the GPL
  component. An app that imports it as a library takes on GPL for that backend. Nothing else in the
  repository imports it.
- **M3** Third-party files keep their notices: the polylabel port (ISC) and the Roboto font (Apache-2.0).
- **M4** Every Python project declares its licence in `pyproject.toml`. No per-file headers.
- **M5** A script checks the licences of resolved Dart and Python dependencies of the MIT modules against an
  allowlist and fails on GPL or unknown. CI runs it.
- **M6** This decision is the repository's licence position. Any other branch that changes licence files
  conforms to it when merged.

## Consequences

- `NOTICE` and the README licensing paragraph are rewritten.
- MIT was chosen over Apache-2.0 because its only condition is keeping the copyright notice.
