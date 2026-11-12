# bond_capture_py
Role: natural-language capture: one note to task and event candidates through a model seam. There is no classifier.
State: implemented (prompt, orchestrator, local answer validation, English and Spanish rule fallback).

## Key files
- `schema.py` `MODEL_SCHEMA` (= `../../fixtures/capture/schema.json`), `RICH_MODEL_SCHEMA` (= `schema_rich.json`), `model_schema`, limits; `candidates.py` wire shapes
- `protocols.py` `LlmClient`, `EntityResolver`, `CaptureGuard`; `errors.py` coded errors
- `prompt.py` + `prompt_v1.md`, `prompt_v2.md` (rich mode; package data); `rich.py` rich fields and end from duration; `capture.py` `parse_capture`; `validate.py` answer checks and mapping; `fallback.py` `degraded_draft`
- `tools/score.py` scores a results dir (or `--run-fallback`) against `../../fixtures/capture/phrases.jsonl`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs. No network in tests; the model is always a fake `LlmClient`.
- Never log the user's text. Contact ids are never sent to the model. Nothing is created from a candidate.
- 300-line soft cap per source file. No secrets, emails or customer data.
