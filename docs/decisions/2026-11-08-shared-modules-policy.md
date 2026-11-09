# 2026-11-08 Shared modules are consumed by pinned SHA

Status: accepted. Supersedes the apps' 2026-10 rule "copy and let them diverge".

## Decision

Shared modules are consumed by pinned SHA; divergence happens only in per-app adapters.

## Why

The apps started as copies and drifted. A fix landed in one copy and never reached the others, and one app
vendored another's sync layer by hand. Copying costs more with every app that joins.

## Consequences

- Apps depend on bond-factory modules by git, full 40-character SHA and `path:` (Dart), or by Poetry
  `git` + `rev` + `subdirectory` or the CI-built wheel (Python). Tags are labels only.
- An app that needs different behaviour writes an adapter in its own repo behind the module's seam
  (a `Protocol`, a `*Labels` object, a policy or hook). It does not edit a vendored copy.
- A needed change in a module goes upstream first, then the app bumps its pin and records it in
  `docs/sdk/sdk-pins.md`. A local patch is temporary and listed there.
- No shared package exposes `flutter_riverpod`, `intl`, `flutter_localizations` or `go_router` in its public
  API. Providers and routing stay in the apps. Strings enter shared widgets through a `*Labels` object with
  English defaults.
- Every Dart package must resolve in a single-package consumer outside the workspace
  (`tool/consumer_check.sh`) and must not pin `intl`.
- CI gates enforce the boundaries: no popups, no raw colours outside tokens, layering, line caps, public hygiene.

See `docs/sdk/README.md` for the consumption steps and `2026-11-08-sdk-architecture.md` for the module set.
