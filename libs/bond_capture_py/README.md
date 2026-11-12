# bond_capture_py

Natural-language capture: one short note becomes task and event candidates for the user to review. The model
sits behind `LlmClient`; there is no classifier. Status: scaffold (0.1.0); the prompt, `parse_capture` and the
fallback are stubs until they are filled in.

## API

- `parse_capture(text, *, user_id, today, time_zone, end_of_day, llm, resolver=None, guard=None, timeout_s=20.0)
  -> CaptureResult`. Creates nothing; never logs the text.
- Seams: `LlmClient.complete_json(system, user, schema, timeout_s)`, `EntityResolver.resolve(user_id, name,
  kind)`, `CaptureGuard.check(user_id, text)` (raises `CaptureDenied`).
- Candidates (frozen dataclasses with `to_dict()` giving the wire shape): `TaskCandidate`, `EventCandidate`,
  `LinkCandidate`, `CaptureResult(items, degraded, reason)`; `reason` is `model_unavailable` or `invalid_output`.
- `MODEL_SCHEMA`: the flat model item schema (also `fixtures/capture/schema.json`); `MAX_TEXT` 500, `MAX_ITEMS`
  8, `MAX_LINKS` 5. Contact ids are never sent to the model.
- `build_prompt`, `fence`, `prompt_v1.md`; `degraded_draft(text, today)` for an unavailable model.
- Errors: `CaptureError`, `LlmUnavailable`, `LlmInvalid`, `CaptureDenied` (429); `text_required` and
  `text_too_long` are 422.

## Regression

`tools/score.py RESULTS_DIR` scores raw model answers (one `NN.txt` per phrase) against
`fixtures/capture/phrases.jsonl`.
