"""The inbox, through bond_notify_py.

    GET  /notices                   ?unread=&limit=&before= -> {items: [Notice], unread_count, next_cursor}
    POST /notices/{id}/read         -> Notice
    POST /notices/{id}/dismiss      -> Notice (a dismissed notice is read too)
    POST /notices/read-all          -> {unread_count}
    POST /notices/{id}/act          {action: "done" | "snooze" | "cancel"} -> {notice, task}

`act` applies the action to the notice's task exactly as the task routes do (a cancel the person may not do is 403
`not_task_owner`), marks the notice read, and on done or cancel puts away every notice of that task. Snooze changes
nothing on the task: the phone re-schedules itself, and the next stage's notice arrives on its own.
404 `notice_not_found`; 403 `not_notice_owner` for another person's notice.
"""

from __future__ import annotations

from typing import Literal

import bond_notify_py as inbox
import bond_tasks_py as tasks
from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from pydantic import BaseModel, ConfigDict

from ..auth_dep import current_user_id, require_capability
from ..models.notices import Notice
from ..models.tasks import Task
from ..task_support import after_write, clock_now, item, unit, viewer_zone

write = require_capability("tasks.write")


class ActBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["done", "snooze", "cancel"]


def register(app: FastAPI) -> None:
    @app.get("/notices")
    def list_notices(request: Request, unread: bool = False, limit: int = Query(50, ge=1, le=200),
                     before: str | None = None, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            rows, unread_count, cursor = inbox.list_notices(session, Notice, user_id, unread=unread, limit=limit,
                                                           before=before)
            return {"items": [inbox.notice_item(r) for r in rows], "unread_count": unread_count,
                    "next_cursor": cursor}

    @app.post("/notices/read-all")
    def read_all(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            inbox.mark_all_read(session, Notice, user_id, clock_now(request))
            return {"unread_count": inbox.list_notices(session, Notice, user_id, unread=True, limit=1)[1]}

    @app.post("/notices/{notice_id}/read")
    def read(notice_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            return inbox.notice_item(inbox.mark_read(session, Notice, user_id, notice_id, clock_now(request)))

    @app.post("/notices/{notice_id}/dismiss")
    def dismiss(notice_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            return inbox.notice_item(inbox.dismiss(session, Notice, user_id, notice_id, clock_now(request)))

    @app.post("/notices/{notice_id}/act")
    def act(notice_id: str, body: ActBody, request: Request, background: BackgroundTasks,
            time_zone: str | None = None, user_id: str = Depends(write)) -> dict:
        now = clock_now(request)
        with unit(request) as session:
            notice = session.get(Notice, notice_id)
            if notice is None:
                raise inbox.NoticeError("notice_not_found")
            if notice.user_id != user_id:
                raise inbox.NoticeError("not_notice_owner")
            task = tasks.get(session, Task, notice.source_id or (notice.data or {}).get("task_id"))
            tasks.apply_notice_action(session, task=task, action=body.action, actor_user_id=user_id, now=now)
            row = inbox.mark_read(session, Notice, user_id, notice_id, now)
            if body.action != "snooze":
                after_write(request, background, session, task)  # done or cancel: every notice of the task goes
            zone = viewer_zone(request, session, user_id, time_zone)
            return {"notice": inbox.notice_item(row), "task": item(request, session, task, zone)}
