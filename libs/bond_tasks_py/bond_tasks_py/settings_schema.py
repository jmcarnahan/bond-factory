"""Input model of the settings update. Every field is optional; check ``model_fields_set``. A field that is
present and null resets it to the app default; an absent field is unchanged."""

from collections.abc import Iterable
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.schema import TIME_PATTERN

Clock = Annotated[str, StringConstraints(pattern=TIME_PATTERN)]


class SettingsUpdate(BaseModel):
    """The shape only. Null on a field means "reset to the default". The service checks that the zone is known and that ``start_of_day`` differs from
    ``end_of_day``."""

    model_config = ConfigDict(extra="forbid")

    time_zone: str | None = Field(default=None, max_length=64)
    start_of_day: Clock | None = None
    end_of_day: Clock | None = None
    lead_minutes: int | None = Field(default=None, ge=0, le=10080)


def settings_item(prefs: UserPrefs, warnings: Iterable[str] = (), overridden: Iterable[str] | None = None) -> dict[str, Any]:
    """The wire shape of the settings routes: the effective preferences as strings, plus the non-blocking warnings.
    With ``overridden`` (the names the user has set, see ``settings_overridden``) the answer also carries
    ``"overridden": [names]``; with None the key is left out (the shape before app defaults existed)."""
    item: dict[str, Any] = {
        "time_zone": prefs.time_zone,
        "start_of_day": prefs.start_of_day.strftime("%H:%M"),
        "end_of_day": prefs.end_of_day.strftime("%H:%M"),
        "lead_minutes": prefs.lead_minutes,
        "warnings": list(warnings),
    }
    if overridden is not None:
        item["overridden"] = list(overridden)
    return item
