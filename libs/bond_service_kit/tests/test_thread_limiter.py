import asyncio
import threading
import time

import anyio

from bond_service_kit import ThreadLimiter, thread_limiter


def test_same_loop_same_name_is_one_limiter_with_its_capacity():
    async def run():
        a = thread_limiter("one", 3)
        assert a is thread_limiter("one", 99) and a.total_tokens == 3
        assert thread_limiter("two", 1) is not a
        return a

    first = asyncio.run(run())
    assert asyncio.run(run()) is not first  # a limiter belongs to the loop that made it


def test_capacity_one_serialises_worker_threads():
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def work():
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1

    async def run(tokens):
        limiter = ThreadLimiter().get("w", tokens)
        async with anyio.create_task_group() as group:
            for _ in range(3):
                group.start_soon(lambda: anyio.to_thread.run_sync(work, limiter=limiter))

    asyncio.run(run(1))
    assert state["max"] == 1
    state["max"] = 0
    asyncio.run(run(3))
    assert state["max"] > 1  # control: with room, they overlap
