# bond_capture_py

Natural-language capture: one short note ("Call Sam tomorrow and lunch with Dana at noon") becomes task and
event candidates for the user to review. Nothing is created here. The model sits behind a Protocol; there is no
classifier and no model SDK dependency (only pydantic and tzdata).

## Main call

```python
result = parse_capture(text, user_id=uid, today=today, time_zone="America/Denver", end_of_day=time(17, 0),
                       llm=my_llm, resolver=my_resolver, guard=my_guard, timeout_s=20.0)
result.to_dict()   # {"items": [TaskCandidate | EventCandidate ...], "degraded": bool, "reason": str | None}
```

Order: strip the text (`text_required`, `text_too_long` over `MAX_TEXT` = 500, both 422); `guard.check`
(`CaptureDenied`, 429); the model call; local validation of the answer; map to candidates; resolve link names.
`today` and `time_zone` come from the caller (the user's day, not the server's).

## The three Protocols

```python
class MyLlm:                                   # LlmClient: any vendor, any SDK
    def complete_json(self, system, user, schema, timeout_s):
        try:
            reply = vendor_client.create(      # your SDK call
                system=system,                 # the rules and examples
                messages=[{"role": "user", "content": user}],   # the fenced note
                json_schema=schema,            # MODEL_SCHEMA, if the vendor supports a schema
                timeout=timeout_s,
                max_tokens=1024,
            )
            return json.loads(reply.text)      # the object, not a string
        except json.JSONDecodeError:
            raise LlmInvalid()                 # unusable answer: draft with reason "invalid_output"
        except (TimeoutError, VendorOutage):
            raise LlmUnavailable()             # draft with reason "model_unavailable"

class MyResolver:                              # EntityResolver: the user's own contacts only
    def resolve(self, user_id, name, kind):    # kind is "contact" unless you pass resolver_kinds
        return [{"id": row.id, "label": row.name} for row in search(user_id, name)]  # best first

class MyGuard:                                 # CaptureGuard: your rate or spend policy
    def check(self, user_id, text):
        if over_limit(user_id):
            raise CaptureDenied()
```

Any other exception from the model also degrades (reason `model_unavailable`). Contact ids never go to the
model: it returns names, the resolver maps them. At most 5 resolver rows are kept per name; a resolver that
raises leaves the name unresolved and the item intact.

## The route an app mounts

`POST /tasks/parse` with `{text, today?, time_zone?}` returns `parse_capture(...).to_dict()`; a `CaptureError`
becomes `{"detail": {"code": err.code, "message": err.message}}` with `err.status` (`CODES` has the table). It
creates nothing: the client shows the candidates (`flags`: `low_confidence` below 0.5; `missed` for an event
dated before today) and the user saves each one through the normal create routes. Two keys go beyond
`fixtures/capture/expected_candidates.json`: the item flag `missed`, and a top-level `dropped` (how many model
items were discarded), present only when above zero. Clients that read `items`, `degraded` and `reason` ignore it.

## Limits and validation

`MAX_TEXT` 500 characters, `MAX_ITEMS` 8 (extra dropped), `MAX_LINKS` 5 per item, titles 255. The answer is
checked locally whatever the vendor promised: shape and kinds, dates and times matched in full and every date
through `date.fromisoformat`, confidence clamped to 0..1 (a priority of 2.0 is 2; other non-integers fail).
One bad item never costs the others: an item that fails any check, has an empty title (after control
characters and bidi overrides are removed from titles and link names) or a date beyond five years is dropped,
and the result's `dropped` count (wire key `dropped`, present only when above zero) lets the UI say so. The
answer is `invalid_output` only when the top level is wrong or no item survives. A task dated in the past
becomes today, `due_defaulted`, with its time cleared; an event with no date becomes a task due today
(`due_defaulted`); a date with no time on an event is all-day; an event end before its start is dropped and an
end time alone ends on the start day; with several `resolver_kinds` a link of an unlisted kind is dropped (with one kind, the default, every link is that kind).

## Rich mode and more link kinds

`parse_capture(..., rich=True)` uses `prompt_v2.md` (marker `CAPTURE-PROMPT-V2`) and `RICH_MODEL_SCHEMA`
(`fixtures/capture/schema_rich.json`). An event candidate gains `location`, `notes`, `duration_minutes` (1 to 10080,
else null) and `attendees` (up to 10 names as written, never resolved, never ids; one with `@` or `://` is dropped).
A wrong type in an optional rich field becomes null (empty for attendees) and the item stays; an explicit end sets `duration_minutes` from start and end.
`location`, `notes` and `attendees` are untrusted model text: never turn them into an address, a link or an id without the user's review. Its end is start plus the length
when the note stated a length and no end, and the event is timed. A task candidate gains `notes`. The wire carries
those keys only for a rich parse (`CaptureResult.to_dict()` follows `result.rich`); the default wire is unchanged
(`expected_candidates.json` still matches byte for byte). Resolver rows keep extra scalar keys (a rank, a type) in
rich mode only. With the model off, a rich parse still answers one plain draft with `notes: null`.
Fixtures: `expected_candidates_rich.json`, `expected_degraded_rich.json`, `model_output_rich.json`, `rich_phrases.json`. The `expected_*_rich.json` fixtures assume a resolver that returns no candidates.

`resolver_kinds=("contact", "place")` lets a link point at more than contacts: the schema enum and one extra prompt
paragraph name the kinds (rule and examples too), and each link's name goes to `resolver.resolve(user_id, name, kind)` with its own kind.
Names are checked (`[a-z][a-z0-9_]*`, at most 24 characters). The default is today's behaviour.

## The degraded fallback

No model (`llm=None`), an outage, or an unusable answer gives ONE task draft from `degraded_draft(text, today)`:
the whole text as title, `degraded: true`, `confidence` 0.2, flag `low_confidence`, never an event. Cheap English
and Spanish rules find the date (today, tonight, tomorrow, weekday names, "next Friday", "in 3 days", "end of
month", "Dec 15th", "15 de diciembre", "2026-11-20", "by 3/5"), the time ("at 3pm", "noon", "a las 9") and the
priority (urgent, asap, low priority, whenever, urgente, cuando pueda). No date found: today, `due_defaulted`
true. Rules: a bare weekday is its next occurrence, "next Friday" is the Friday of next week (weeks start
Monday); a numeric "M/D" counts only after by, on, before, due, para or el, US order unless the first number
is above 12 ("31/12"); a bare hour from 1 to 6 is pm ("at 3" 15:00, "at 6:30" 18:30) unless the phrase has a
morning word ("tomorrow morning at 6:30" is 06:30).

## Never logged

The note, the model's answer, titles, link names and vendor error messages are never logged. Logs carry text
length, item counts, the reason and exception type names only (a test proves it with `caplog`). The note goes
to the model HTML-escaped inside `<untrusted_text>` tags, so it cannot close the fence.

## Scoring the prompt

`fixtures/capture/phrases.jsonl` holds 60 labelled phrases (kind, date, time, count, injection checks; "either"
where a person could not decide), written for today = 2026-11-11. Run each phrase through your model with
`build_prompt(date(2026, 11, 11), "Wednesday", "UTC", time(17, 0))` and `fence(text)`, save the raw answer of
phrase N as `N:02d.txt` in a directory, then:

```
python tools/score.py RESULTS_DIR --misses        # the prompt's regression table
python tools/score.py --run-fallback --misses     # the rule fallback on the single-task phrases
```

Prompt changes keep the marker line (`CAPTURE-PROMPT-V1`, or `CAPTURE-PROMPT-V2` for rich mode) and the six required
examples; re-score before shipping. For rich mode pass `--schema ../../fixtures/capture/schema_rich.json`.
