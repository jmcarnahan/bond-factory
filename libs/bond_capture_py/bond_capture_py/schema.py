"""The model's answer schema: one flat item shape, every property required, nullable by type.

The server maps each item to a ``TaskCandidate`` or ``EventCandidate``. Contact ids are never sent to the model.
``fixtures/capture/schema.json`` is this dict as JSON; a test asserts they are equal.
"""

import copy
import re

MAX_TEXT = 500  # characters of user text accepted
MAX_ITEMS = 8  # items the model may return
MAX_LINKS = 5  # links per item

_DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
_TIME = {"type": ["string", "null"], "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"}

MODEL_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CaptureModelOutput",
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "title", "date", "time", "due_defaulted", "priority", "all_day", "end_date",
                             "end_time", "links", "confidence"],
                "properties": {
                    "kind": {"type": "string", "enum": ["task", "event"]},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "date": dict(_DATE),
                    "time": dict(_TIME, type=["string", "null"]),
                    "due_defaulted": {"type": "boolean"},
                    "priority": {"type": ["integer", "null"], "minimum": 1, "maximum": 3},
                    "all_day": {"type": "boolean"},
                    "end_date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                    "end_time": dict(_TIME),
                    "links": {
                        "type": "array",
                        "maxItems": MAX_LINKS,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["text", "kind"],
                            "properties": {
                                "text": {"type": "string", "minLength": 1, "maxLength": 80},
                                "kind": {"type": "string", "enum": ["contact"]},
                            },
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}

DEFAULT_KINDS = ("contact",)  # what a link may point at unless the app passes ``resolver_kinds``
MAX_ATTENDEES = 10  # names per event in rich mode
MAX_DURATION = 7 * 24 * 60  # minutes; a longer stated length is a model slip and is dropped to null
LOCATION_CAP, NOTES_CAP, ATTENDEE_CAP = 200, 1000, 80
_KIND = re.compile(r"[a-z][a-z0-9_]{0,23}", re.ASCII)

_RICH_PROPERTIES = {
    "location": {"type": ["string", "null"], "maxLength": LOCATION_CAP},
    "notes": {"type": ["string", "null"], "maxLength": NOTES_CAP},
    "duration_minutes": {"type": ["integer", "null"], "minimum": 1, "maximum": MAX_DURATION},
    "attendees": {"type": "array", "maxItems": MAX_ATTENDEES,
                  "items": {"type": "string", "minLength": 1, "maxLength": ATTENDEE_CAP}},
}


def check_kinds(kinds) -> tuple[str, ...]:
    """The link kinds an app resolves: a non-empty sequence of distinct lower-case names (``[a-z][a-z0-9_]*``,
    at most 24 characters). ``ValueError`` otherwise (``TypeError`` for a bare string): the names go into the prompt, so they are checked."""
    if isinstance(kinds, str):
        raise TypeError("resolver_kinds is a sequence of names, not one string")
    out = tuple(kinds)
    if not out or len(set(out)) != len(out) or not all(isinstance(k, str) and _KIND.fullmatch(k) for k in out):
        raise ValueError("resolver_kinds must be distinct names such as 'contact'")
    return out


def model_schema(rich: bool = False, kinds=DEFAULT_KINDS) -> dict:
    """The schema for one call. The default arguments give ``MODEL_SCHEMA`` itself. ``rich`` adds the four rich
    properties (all required, nullable); ``kinds`` is the enum of a link's kind."""
    kinds = check_kinds(kinds)
    if not rich and kinds == DEFAULT_KINDS:
        return MODEL_SCHEMA
    schema = copy.deepcopy(MODEL_SCHEMA)
    item = schema["properties"]["items"]["items"]
    item["properties"]["links"]["items"]["properties"]["kind"]["enum"] = list(kinds)
    if rich:
        item["properties"].update(copy.deepcopy(_RICH_PROPERTIES))
        item["required"] = [*item["required"], *_RICH_PROPERTIES]
    return schema


RICH_MODEL_SCHEMA: dict = model_schema(rich=True)  # = ``../../fixtures/capture/schema_rich.json``
