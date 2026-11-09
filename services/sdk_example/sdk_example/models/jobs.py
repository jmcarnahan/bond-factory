"""The example's background job table (the mixin owns the columns and the claim index)."""

from bond_jobs import JobsMixin

from ..db import Base


class BackgroundJob(JobsMixin, Base):
    pass
