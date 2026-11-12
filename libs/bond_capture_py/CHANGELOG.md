# Changelog

## 0.1.0 - unreleased
- `LlmClient`, `EntityResolver`, `CaptureGuard`, candidates with `to_dict`, `MODEL_SCHEMA`, limits, coded errors,
  `prompt_v1.md`, `tools/score.py`.
- `build_prompt`, `fence`, `parse_capture` (guard, model call, local validation, link resolution, degraded
  fallback with `model_unavailable` or `invalid_output`), `degraded_draft` (English and Spanish rules; a
  `TaskCandidate` dict). An event that started before today carries the flag `missed`.
- Two additions to the wire. Top-level key `dropped` in the `parse_capture(...).to_dict()` result: how many
  items the model returned that were discarded (invalid, empty title, date beyond five years, past the item
  limit); present only when above zero, so clients that ignore unknown keys and the shape of
  `expected_candidates.json` are unaffected. Item flag `missed` (in `flags`, beside `low_confidence`): an event
  dated before today; never "overdue", which is for tasks.
- One bad item never costs the others (a hostile number such as 1e400 drops its item); the answer is
  `invalid_output` only for a wrong top level or when no item survives.
- `fixtures/capture/phrases.jsonl` phrase 52 accepts 3 or 4 items (was exactly 3): the model reads "...tell
  Marcus I am out Wednesday" as three tasks plus an all-day "Out of office" event in every run of the
  2026-11-11 measurement (`docs/research/2026-11-11-capture-prompt/README.md`); both readings are acceptable.
  `tools/score.py` pairs a keyword label with the item of the labelled kind first.
- `tools/score.py --run-fallback`; `fixtures/capture/phrases.jsonl` grows to 60 phrases.
