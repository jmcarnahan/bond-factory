"""/health must answer while the sync-route thread pool is saturated."""

import asyncio
import time

import httpx
from fastapi import FastAPI

from bond_service_kit import health_router

ROUTES = 45  # more than anyio's default 40 worker threads
HOLD = 1.5


def make_app():
    app = FastAPI()
    app.include_router(health_router({"db": lambda: True}, timeout=1.0))

    @app.get("/slow")
    def slow():
        time.sleep(HOLD)
        return {}

    return app


async def scenario():
    transport = httpx.ASGITransport(app=make_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        slow = [asyncio.create_task(client.get("/slow")) for _ in range(ROUTES)]
        await asyncio.sleep(0.4)  # every default worker thread is now busy and 5 routes are queued
        started = time.monotonic()
        response = await client.get("/health")
        elapsed = time.monotonic() - started
        await asyncio.gather(*slow)
    return response, elapsed


def test_health_answers_200_while_sync_routes_saturate_the_default_pool():
    response, elapsed = asyncio.run(scenario())
    assert response.status_code == 200 and response.json() == {"status": "ok", "checks": {"db": "ok"}}
    assert elapsed < 0.5
