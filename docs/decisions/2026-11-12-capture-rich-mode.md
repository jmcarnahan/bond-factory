# 2026-11-12 Capture rich mode

Status: accepted. Dated, append-only.

## Context

A parsed event carried a title and times only. Apps wanted a location, notes, a length and who is invited, and a note on
a task. The prompt that makes the model return them is larger and costs more per call, so it cannot be the default.

## Decisions

- `parse_capture(rich=False)` is the default and its wire is byte-identical to before. `rich=True` uses `prompt_v2.md`
  and the rich schema. Events gain `location`, `notes`, `duration_minutes` (their end is the start plus the length when
  no end was stated) and `attendees`; tasks gain `notes`. The extra keys appear only in a rich answer.
- Attendees are names as the person said them. They are never resolved to people or contacts and never leave the model
  call as ids. The calendar lib takes `attendees: str | Person`, so a host that has resolved a name may pass a `Person`.
- `resolver_kinds` lists what a link may point at (default: the one kind as before). Each link name is resolved with its
  own kind through `resolver.resolve(user_id, name, kind)`. In rich mode a resolver row keeps extra scalar keys.
- The example's `POST /tasks/parse` takes `rich` in the body (default false). Its fake model answers with
  `fixtures/capture/model_output_rich.json` when the schema asks for rich fields. The example has one link kind, so it
  does not pass `resolver_kinds`.

## Measured and not measured

Read the "Known limits" section of `docs/migration/bond_capture_py.md` for the numbers: they are small-tier, prompt-only,
20 made-up phrases. Not measured: `resolver_kinds` prompting, larger tiers, other vendors, non-English notes. Score with
your own model before relying on rich mode.
