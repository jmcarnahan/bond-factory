"""The pin set by `PUT /fake/clock`, as the kit's `fake_clock_router` sees it.

The app clock is the kit `Clock` (`app.state.clock`); every route, the sweep and sync read it. The router needs to know
two more things: whether a pin was SET THROUGH THE ROUTE (a test fixture or `/jobs/tick` may also freeze the clock, and
neither counts), and what it is. `app.state.clock_pin` keeps that. `/jobs/tick` pins its own time for one pass and then
goes back to this pin, or releases the clock when there is none.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI

from .wiring import set_now


class RoutePin:
    """`PinnableClock` over `app.state.clock_pin`: freezing and releasing move the real app clock too."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    @property
    def frozen(self) -> bool:
        return self.app.state.clock_pin is not None

    def now(self) -> datetime:
        return self.app.state.clock_pin

    def freeze(self, at: datetime) -> None:
        self.app.state.clock_pin = at
        set_now(self.app, at)

    def unfreeze(self) -> None:
        self.app.state.clock_pin = None
        set_now(self.app, None)
