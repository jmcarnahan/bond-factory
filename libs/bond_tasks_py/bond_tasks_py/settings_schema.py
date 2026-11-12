"""Input model of the settings update. Every field is optional; check ``model_fields_set``."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from bond_tasks_py.schema import TIME_PATTERN

Clock = Annotated[str, StringConstraints(pattern=TIME_PATTERN)]


class SettingsUpdate(BaseModel):
    """The shape only. The service checks that the zone is known and that ``start_of_day`` differs from
    ``end_of_day``."""

    model_config = ConfigDict(extra="forbid")

    time_zone: str | None = Field(default=None, max_length=64)
    start_of_day: Clock | None = None
    end_of_day: Clock | None = None
    lead_minutes: int | None = Field(default=None, ge=0, le=10080)
