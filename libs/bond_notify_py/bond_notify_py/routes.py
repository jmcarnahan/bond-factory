"""``make_notices_router``: the inbox routes behind one call. Needs fastapi (extra ``http``); import it as
``bond_notify_py.routes`` only. The package ``__init__`` never imports this file.

    GET  {prefix}                  ?unread=&limit=&before= -> {items, unread_count, next_cursor}
    POST {prefix}/read-all         -> {unread_count}
    POST {prefix}/{id}/read | /dismiss   -> Notice
    POST {prefix}/{id}/act         {action} -> {notice, **on_act result}   (only with ``on_act``)

A ``NoticeError`` answers ``exc.status`` with ``{"detail": {"code", "message"}}`` (404 ``notice_not_found``,
403 ``not_notice_owner``). So does any other exception that carries a str ``code``, a str ``message`` and an int
``status`` (for example a coded error raised by ``on_act``), unless it has its own ``detail`` (an app error class with
its own handler). ``error_map`` replaces this rule.
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ConfigDict, create_model

from bond_notify_py import service
from bond_notify_py.errors import NoticeError
from bond_notify_py.serialize import notice_item

ErrorMap = Callable[[Exception], "tuple[int, Any] | None"]


def _coded(exc: Exception) -> tuple[int, Any] | None:
    """The default answer: a ``NoticeError``, or anything shaped like one (``code`` str, ``message`` str, ``status``
    int). An exception with its own ``detail`` is left to the app's handler for it."""
    if hasattr(exc, "detail") and not isinstance(exc, NoticeError):
        return None
    code, message, status = (getattr(exc, name, None) for name in ("code", "message", "status"))
    if isinstance(code, str) and isinstance(message, str) and isinstance(status, int) and not isinstance(status, bool):
        return status, {"detail": {"code": code, "message": message}}
    return None


def _mapped(error_map: ErrorMap, exc: Exception) -> tuple[int, Any] | None:
    """``error_map(exc)`` returns ``(status: int, body)`` or None (re-raise). Anything else, or a raise, is a
    ``TypeError`` that names ``error_map`` and keeps the original exception as its cause."""
    try:
        answer = error_map(exc)
    except Exception as err:  # noqa: BLE001
        raise TypeError(f"error_map raised {type(err).__name__}: {err}") from exc
    if answer is None:
        return None
    if (not isinstance(answer, tuple) or len(answer) != 2 or isinstance(answer[0], bool)
            or not isinstance(answer[0], int)):
        raise TypeError(f"error_map must return (status: int, body) or None, got {answer!r}") from exc
    return answer


def _route_class(error_map: ErrorMap | None) -> type[APIRoute]:
    class GuardedRoute(APIRoute):
        def get_route_handler(self) -> Callable:
            inner = super().get_route_handler()

            async def handler(request: Request) -> Response:
                try:
                    return await inner(request)
                except Exception as exc:
                    answer = _mapped(error_map, exc) if error_map is not None else _coded(exc)
                    if answer is None:
                        raise
                    status, body = answer
                    return JSONResponse(status_code=status, content=body)

            return handler

    return GuardedRoute


def make_notices_router(
    *, notice_model: Any, session_scope: Callable[[], AbstractContextManager[Any]], user_dep: Callable,
    now: Callable[[], datetime],
    on_act: Callable[[Any, Any, str, str, datetime], Mapping[str, Any] | None] | None = None,
    prefix: str = "/notices",
    # Added beyond the planned signature; each defaults to the behaviour without it.
    act_dep: Callable | None = None, actions: Sequence[str] = ("done", "snooze", "cancel"),
    after_act: Callable[[Any, Any, Mapping[str, Any] | None], None] | None = None,
    error_map: ErrorMap | None = None,
) -> APIRouter:
    """Mount with ``app.include_router``. ``session_scope()`` is a context manager factory: commit on exit, roll back
    on an exception. ``user_dep`` returns the caller's user id; ``now()`` is naive UTC.

    ``on_act(session, notice, action, user_id, now)`` is called after ``get_owned`` proved the notice is the caller's;
    it applies the action (for a task notice: to the task) and may return a mapping merged into the answer next to
    ``notice``. After it, the notice is marked read. With ``on_act`` None the act route is not mounted. ``act_dep`` is an
    extra dependency of the act route. ``actions`` are the accepted action names (others are a 422 validation error).
    ``after_act(background, notice, result)`` queues work after the response. ``error_map(exc)`` is asked for any
    exception that escapes a route: a ``(status, body)`` answer is the response, None re-raises it. Without it the
    coded-exception rule in the module docstring applies. In the act answer ``notice`` always wins over a result key."""
    router = APIRouter(prefix=prefix, route_class=_route_class(error_map), tags=["notices"])

    @router.get("")
    def list_notices(unread: bool = False, limit: int = Query(50, ge=1, le=200), before: str | None = None,
                     user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            rows, unread_count, cursor = service.list_notices(session, notice_model, user_id, unread=unread,
                                                              limit=limit, before=before)
            return {"items": [notice_item(r) for r in rows], "unread_count": unread_count, "next_cursor": cursor}

    @router.post("/read-all")
    def read_all(user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            service.mark_all_read(session, notice_model, user_id, now())
            return {"unread_count": service.list_notices(session, notice_model, user_id, unread=True, limit=1)[1]}

    @router.post("/{notice_id}/read")
    def read(notice_id: str, user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            return notice_item(service.mark_read(session, notice_model, user_id, notice_id, now()))

    @router.post("/{notice_id}/dismiss")
    def dismiss(notice_id: str, user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            return notice_item(service.dismiss(session, notice_model, user_id, notice_id, now()))

    if on_act is not None:
        act_body = create_model("ActBody", __config__=ConfigDict(extra="forbid"),
                                action=(Literal[tuple(actions)], ...))  # type: ignore[valid-type]

        @router.post("/{notice_id}/act", dependencies=[Depends(act_dep)] if act_dep is not None else [])
        def act(notice_id: str, body: act_body, background: BackgroundTasks,  # type: ignore[valid-type]
                user_id: str = Depends(user_dep)) -> dict:
            moment = now()
            with session_scope() as session:
                notice = service.get_owned(session, notice_model, user_id, notice_id)  # first: on_act never sees others'
                result = on_act(session, notice, body.action, user_id, moment)
                row = service.mark_read(session, notice_model, user_id, notice_id, moment)
                if after_act is not None:
                    after_act(background, notice, result)
                return {"notice": notice_item(row), **{k: v for k, v in dict(result or {}).items() if k != "notice"}}

    return router
