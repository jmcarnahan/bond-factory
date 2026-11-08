---
paths: ["services/**", "libs/**"]
---
# Python modules

- Scoped runs: `.venv/bin/pytest tests/test_x.py` or `-k <name>`. Never the whole suite mid-task.
- Lint: `make lint` (ruff) in the module, before handing back.
- Tests never touch the network unless marked `network`; those run only with `<MODULE>_NETWORK=1` (roof_measure: `ROOF_MEASURE_NETWORK=1`).
- Never read `tests/data/**`; the deny rule in .claude/settings.json blocks it.
- uv workspace: one `uv.lock` at the repo root. Never read it; change deps in the module's pyproject.toml.
- Build a wheel with `uv build --package <name>`.
- Modules sit at depth 2 (`services/<x>`, `libs/<x>`); shared fixtures are at `../../fixtures`.
- Output dirs (`cache/`, `out/`, `.venv/`) are gitignored. Do not commit them.
- Keep source files under about 300 lines; split when next touched.
- Public repo: no keys, emails or customer data in code, tests or fixtures.
