"""The model's answer schema: one flat item shape, every property required, nullable by type.

The server maps each item to a ``TaskCandidate`` or ``EventCandidate``. Contact ids are never sent to the model.
``fixtures/capture/schema.json`` is this dict as JSON; a test asserts they are equal.
"""

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
