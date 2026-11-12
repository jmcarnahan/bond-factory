"""Phone registration, through bond_push_py. `user_id` always comes from the session, never the body.

    POST   /push/devices                 {device_id, token, platform, environment, topic?} -> 201 {device_id}
    DELETE /push/devices/{device_id}     204 (deleting what is gone is success)

Re-posting the same device updates its token and `last_seen_at`. A phone that syncs may write its own row through the
sync upload route instead (`push_devices`, see routes/sync.py).
"""

from __future__ import annotations

import bond_push_py as push
from fastapi import Depends, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict

from ..auth_dep import current_user_id
from ..models.push import PushDevice
from ..task_support import clock_now, unit


class DeviceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    token: str
    platform: str
    environment: str
    topic: str | None = None


def register(app: FastAPI) -> None:
    @app.post("/push/devices", status_code=201)
    def register_device(body: DeviceBody, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            row = push.register_device(session, PushDevice, user_id=user_id, device_id=body.device_id,
                                       token=body.token, platform=body.platform, environment=body.environment,
                                       topic=body.topic, now=clock_now(request))
            return {"device_id": row.device_id}

    @app.delete("/push/devices/{device_id}", status_code=204)
    def unregister_device(device_id: str, request: Request, user_id: str = Depends(current_user_id)) -> Response:
        with unit(request) as session:
            push.unregister_device(session, PushDevice, user_id=user_id, device_id=device_id)
        return Response(status_code=204)
