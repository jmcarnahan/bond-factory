"""Settings over sync: the route of the per-user settings table (one row per user, the row id is the user id).

``settings_routes(settings_model, task_model, ...)`` returns ``{(settings_model.__tablename__, None): TaskRoute}`` with
the same four fields as ``sync_routes`` (wrap it as the sync lib's ``Route``). Put and patch mean the same: a key present
with null resets that setting to the app default, an absent key is unchanged, and no row yet is created. The handler calls
``update_settings`` in the op's transaction, so the user's date-only due instants are recomputed there.

``op.id`` must be the session user's id (else ``forbidden``, code ``not_settings_owner``); the payload never names the user
(a ``user_id`` key is ignored, like any unknown key). A bad ``HH:MM``, zone or lead raises ``TaskError`` with the code
``invalid_<field>`` (and ``invalid_work_day`` for equal start and end); ``settings_verdict_for`` maps it, so nothing but
that error leaves the handler. The write runs in a savepoint and is retried once if a concurrent first write took the
row (a second failure, or any other integrity failure of the app's table, is a ``conflict`` verdict,
``settings_conflict``). There is no delete op. The server's warnings do not travel over sync.
"""

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from bond_tasks_py import usersettings
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.settings_schema import SettingsUpdate
from bond_tasks_py.sync_routes import TaskRoute, actor_of, verdict_for
from bond_tasks_py.timeutil import utcnow

SETTINGS_FIELDS = ("time_zone", "start_of_day", "end_of_day", "lead_minutes")


def settings_routes(settings_model: Any, task_model: Any, *, now: Callable = utcnow, defaults: UserPrefs | None = None,
                    tz: str = "UTC", on_recomputed: Callable[[Any, Any, Any, Any], None] | None = None) -> dict:
    """``tz`` is the app default zone and ``defaults`` the app's ``UserPrefs`` (both as for ``update_settings``);
    ``on_recomputed(session, task, old_due_at, now)`` follows each due instant a change moved."""

    def handler(session: Any, ctx: Any, op: Any, data: dict) -> None:
        if str(op.id) != str(actor_of(ctx)):  # an op id is text; an app's user id may be an integer
            raise TaskError("not_settings_owner", "A settings row belongs to its user.", 403)
        lead = data.get("lead_minutes")
        if isinstance(lead, bool) or (isinstance(lead, float) and not lead.is_integer()):
            raise TaskError("invalid_lead_minutes")  # pydantic's lax int takes True and 1.0
        try:
            body = SettingsUpdate.model_validate({k: data[k] for k in SETTINGS_FIELDS if k in data})
        except ValidationError as exc:
            raise TaskError(f"invalid_{exc.errors()[0]['loc'][0]}") from exc
        moment = now()

        def moved(task: Any, old_due_at: Any) -> None:
            if on_recomputed is not None:
                on_recomputed(session, task, old_due_at, moment)

        for attempt in (1, 2):  # two first puts at once: the loser's insert fails, its retry finds the row and updates it
            try:
                with session.begin_nested():
                    usersettings.update_settings(session, settings_model=settings_model, task_model=task_model,
                                                 user_id=op.id, data=body, tz=tz, now=moment, on_recomputed=moved,
                                                 defaults=defaults)
                return
            except IntegrityError as exc:
                if attempt == 2:
                    raise TaskError("settings_conflict", "The settings row changed under this write.", 409) from exc

    return {(settings_model.__tablename__, None): TaskRoute(frozenset({"put", "patch"}), handler, SETTINGS_FIELDS)}


def settings_verdict_for(exc: Exception) -> tuple[str, str] | None:
    """``(sync verdict code, message)`` for a settings refusal (the codes of ``verdict_for``), else None."""
    return verdict_for(exc)
