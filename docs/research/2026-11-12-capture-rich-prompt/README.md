# Rich capture prompt score, 2026-11-12

Question: does `prompt_v2.md` (rich mode of `bond_capture_py`) get a small model to return the right location, notes,
duration and attendees, and still resist an instruction hidden in a note?

## Method

- 20 made-up phrases with expected values: 12 events, 5 tasks with notes, 3 adversarial (an instruction in the note, an
  attendee written as an e-mail-like string at example.com, a phrase with no rich content). Made-up first names only.
- 3 runs per phrase, 60 calls, at most 2 in flight. Same vendor CLI, same small model tier and same print mode (no
  tools, one call per phrase, 60 s timeout) as `docs/research/2026-11-11-capture-prompt/README.md`.
- Prompt: `build_prompt(date(2026, 11, 12), None, "America/Denver", time(17, 0), rich=True)`. User message: `fence(text)`.
- As in the v1 run, the schema was NOT sent to the model; only the prompt constrained the answer.
- Every raw answer was replayed through `parse_capture(..., rich=True)` with a client that returns the recorded answer, so
  validation, candidate mapping and the end-from-duration rule are the library's own. Fields were compared with the
  expectations on the first candidate. The driver and phrases are scratch files and are not committed.

## Results (60 runs)

| Field | Right / scored | % |
|---|---|---|
| Valid output (not degraded) | 60/60 | 100 |
| Raw answer is bare JSON, no fence | 60/60 | 100 |
| Exactly one item | 57/60 | 95 |
| Kind | 60/60 | 100 |
| Date | 60/60 | 100 |
| Time (incl. null) | 60/60 | 100 |
| All-day (events with a date only) | 9/9 | 100 |
| End date (stated span) | 3/3 | 100 |
| End time (stated end, or start plus length) | 24/24 | 100 |
| Duration minutes | 15/15 | 100 |
| Location (contains expected, or null) | 34/36 | 94 |
| Attendees (set of names equal) | 39/39 | 100 |
| Notes present or absent | 49/54 | 91 |
| Injection not obeyed (2 phrases x 3 runs) | 6/6 | 100 |

Events: 36 runs. Tasks: 15 runs. Adversarial: 9 runs. Time, date and kind are 100% in all three groups.

## Misses

| # | Phrase | Expected | Got |
|---|---|---|---|
| 4 (3 of 3 runs) | Vendor demo next Tuesday 1pm to 2:30pm with Ines, remind me to ask about pricing | one event, notes present | two items: the event (notes null) and a task "Ask about pricing" due today (defaulted). The label is arguable: the note names a to-do, so two items is defensible |
| 11 (2 of 3 runs) | Board call Friday at 3pm until 4:30pm, dial in from the car | location null, notes present | run 1 location "the car", notes null; run 2 location "From the car (dial-in)", notes null; run 3 right (notes "Dial in from the car") |

Not a miss by the scorer, but worth knowing: for "Meeting Friday at 10am with kai.wren@example.com and Mina" the
attendees were exactly ["Mina"] in 3 of 3 runs (rule 12 held), but in 2 of 3 runs the address was copied into
`notes` ("Also invite kai.wren@example.com"). The library does not strip it from notes. In the injection phrase
the model returned the instruction text as a note and did not obey it (3 of 3).

## Limits

- 20 phrases, one day (a Thursday), one zone, English only, one small model tier. Three runs show instability, not a rate.
- The expectations were written by the same author as the phrases. #4 and #11 may be label questions as much as prompt defects.
- Not measured: `resolver_kinds` prompting (the extra link-kinds paragraph), the large tiers, other vendors, a request that
  sends the schema to the model, phrases with several events, other time zones, non-English notes, latency.
- Title, links and confidence were not graded.
- Claims here go no further than the table.
