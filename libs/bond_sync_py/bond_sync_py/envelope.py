"""Wire shapes for the upload route: a queue of local writes in, one verdict per op out."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_OPS = 100


def server_now_iso(now: datetime | None = None) -> str:
    """ISO 8601 UTC with milliseconds and a trailing Z. A naive ``now`` is taken as UTC; an aware one is converted."""
    moment = now or datetime.now(UTC)
    moment = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class UploadOp(BaseModel):
    """One queued local write. The id pattern is checked per op by the dispatcher, so one bad id is one verdict, not a 422."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    op: Literal["put", "patch", "delete"]
    table: str = Field(min_length=1, max_length=64)
    id: str = Field(max_length=256)
    action: str | None = Field(default=None, min_length=1, max_length=32)
    data: dict = Field(default_factory=dict)


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: int | None = None
    ops: list[UploadOp] = Field(max_length=MAX_OPS)

    @field_validator("ops")
    @classmethod
    def _unique_seq(cls, ops: list[UploadOp]) -> list[UploadOp]:
        seqs = [o.seq for o in ops]
        if len(set(seqs)) != len(seqs):
            raise ValueError("seq values must be unique")
        return ops


class OpResult(BaseModel):
    """The verdict for one op: ``ok`` (maybe ``resolved_id``), ``rejected`` (``code``, ``message``) or ``skipped`` (``code``)."""

    seq: int
    status: Literal["ok", "rejected", "skipped"]
    code: str | None = None
    message: str | None = None
    resolved_id: str | None = None

    def wire(self) -> dict:
        """The JSON object sent to the device: unset keys are absent."""
        return self.model_dump(exclude_none=True)


class UploadResponse(BaseModel):
    results: list[OpResult]
    server_now: str

    def wire(self) -> dict:
        return {"results": [r.wire() for r in self.results], "server_now": self.server_now}
