import time
from datetime import datetime

from bond_sync_py.envelope import server_now_iso


def test_naive_now_is_taken_as_utc_on_a_non_utc_host(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        assert server_now_iso(datetime(2030, 1, 2, 3, 4, 5, 678000)) == "2030-01-02T03:04:05.678Z"
    finally:
        monkeypatch.undo()
        time.tzset()
