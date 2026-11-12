# 2026-11-12 Themable corner shape in bond_ui

Status: accepted. Dated, append-only.

## Context

Corner radii were constants (`BondRadius.r4` to `r20`). An app with a squarer or rounder look had to fork widgets.

## Decisions

- `BondShape` holds the five steps (`r4, r8, r12, r16, r20` and their `...All` forms) and lives in
  `BondTokens.shape`. The default `const BondShape()` has the old values, so nothing changes until an app sets it.
- Every widget reads its radii from `BondTokens.of(context).shape`.
- `BondRadius.rN` and `rNAll` stay for one release as `@Deprecated` aliases. Move to the token.
- The pill is not themable: `BondRadius.pill` stays a constant, because a pill is a shape rule, not a step.
- Spacing and text sizes stay constants. They are a scale, and an app that wants another scale needs another design.

## Consequences

The demo reads no `BondRadius.rN`, so it needed no change.
