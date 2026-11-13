# 2026-11-12 Adopter proof: failing tests, not reading

Status: accepted. Dated, append-only. Extends 2026-11-08-shared-modules-policy.md.

## Context

Two rounds of gap-finding by reading code missed things. The example service is a new build: its columns, wire and
clients are whatever the modules prefer, so it can never collide with them. An app that already exists has columns
with other names, a response shape that installed clients read, its own error codes and an old client in the field.
Those collisions appear only when tests run against that shape.

## Decisions

- **P1** An app never waits on the shared modules. It adapts in its own adapter and ships. A request to the modules is
  an improvement, not a gate.
- **P2** A request arrives as a failing test and, where possible, a patch that makes it pass. The test lives in the
  legacy host (`services/legacy_host`) or comes from an adopter's own battery run by `make adopter-check`. Prose lists
  from reading code are not accepted.
- **P3** A module is not "ready to adopt" until the legacy host exercises it.
- **P4** The legacy host has eight traits, each with tests in `make test`:

  | Trait | What it proves |
  |---|---|
  | Legacy column names | the module works over columns the app already named differently |
  | App-owned columns | columns the module does not know survive its writes and reads |
  | Legacy wire | the installed response shape and error codes are produced by the app's adapter |
  | Old client in the field | a client that predates the module still works unchanged |
  | New client on the old wire | the shared client reads the legacy shape through its adapter |
  | Existing tables | the module attaches to tables and data that already exist |
  | Partial ownership of an external record | the app owns some fields of a record another system also writes |
  | An existing phone database | the phone store works over a local table the app already ships (missing columns, renamed flag, app columns, old rows, joined tables); checklist ticks and untick, and per-user settings over sync, are part of it |

- **P5** `make adopter-check APP=<path>` is opt-in and local, because apps are separate repositories. Run it for each
  known adopter before a merge to `main` that changes a module that adopter pins.
- **P6** A gap the host exposes is fixed in the module, or recorded as a limit in the module's migration note, in the
  same change. A fix is either a generic seam the host opts into (default behaviour unchanged), or a tolerant-reader
  change that alters only how malformed, blank or NULL input is treated. Any default that does change is named in the
  module's CHANGELOG.

Amended 2026-11-12: eighth trait added (round 3)
