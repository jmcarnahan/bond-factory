# docs index

- contracts/roof_model.md — the `bond.roof_model/0.1` wire contract shared by bond_roof and roof_measure
- decisions/2026-11-07-roof-poc-summary.md — what the roof POC proved and what was decided
- contracts/error_body.md — the shared error body, status codes and Retry-After rules (bond_api, bond_service_kit)
- contracts/auth.md — auth routes, user shape, session JWT, revocation, error codes, providers payload
- decisions/2026-11-08-shared-modules-policy.md — shared modules are consumed by pinned SHA; divergence only in per-app adapters
- decisions/2026-11-08-sdk-architecture.md — the shared SDK decisions D1 to D14 and the module list
- ../libs/bond_signin/README.md — direct Google/Microsoft sign-in lib: Protocol seams, scope policy, router factory (no sibling bond_* imports)
- ../packages/bond_signin/README.md — pure-Dart sign-in client: attempts, returns, OIDC session gateway
- ../packages/bond_signin_ui/README.md — sign-in screen, buttons, scope-ask card, system-browser port
- sdk/README.md — how an app consumes bond-factory (Dart git + SHA, Python Poetry or wheel), versioning, module index
- sdk/sdk-pins.md — template an app copies to record its pins and local patches
- test/WEB.md — Playwright walk recipe for demos/sdk_demo
- research/2026-11-07-roof-poc/README.md — research index for the POC
  - dart-diagrams/FINDINGS.md — Dart diagram rendering findings
  - footprints/FINDINGS.md — building footprint sources
  - lidar-3dep/FINDINGS.md — USGS 3DEP LiDAR access and fit
  - roof-algos/FINDINGS.md — plane and level algorithms
  - ground-truth/ — reference reports and checks (no FINDINGS.md)
  - solar-agent-track/agent_design.md — Solar + agent design
- ../fixtures/README.md — contract fixtures

## Rules
- contracts/ is normative, decisions/ is dated and append-only, research/ is evidence.
- Research folders hold text and images under 300 KB only.
- Name new files `YYYY-MM-DD-<slug>` in decisions/ and research/.
