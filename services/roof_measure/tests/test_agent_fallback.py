"""An agent method never becomes a new way to fail: it falls back to the rule result, and says so.

``lidar_agent`` (and ``solar_agent``) that hit an AgentError, a shapely error, a timeout of the agent stage, or
blocks the model builder rejects return the deterministic result with the warning code ``agent_failed_fell_back``.
``lidar_skeleton`` and ``auto`` are untouched. Offline: scripted clients, no key, no network.
"""

import json
import signal
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest
from conftest import FIXTURES
from shapely.errors import GEOSException

import roof_measure._isolate as isolate
import roof_measure.library
from roof_measure import agent as agent_mod
from roof_measure import pipeline
from roof_measure.deadline import Deadline, DeadlineExceeded
from roof_measure.envelope import WARNING_CODES
from roof_measure.library import MeasureError, measure
from roof_measure.model import ModelError

BLOCKS = FIXTURES / "site1_blocks.json"
SOLAR = FIXTURES / "synthetic_solar_response.json"
ENTRY = Path(__file__).with_name("crash_child_entry.py")
CODE = "agent_failed_fell_back"
ADDR = "100 Example Ave, Sampletown, CA 90000"
FLAT_FINAL = {"blocks": [{"polygon_id": "footprint", "form": "flat", "confidence": "low", "evidence": ["x"]}]}


class Client:
    """Scripted client: ``replies`` are lists of tool calls, or an exception instance to raise."""

    def __init__(self, *replies, stop="tool_use"):
        self.replies = list(replies)
        self.messages = NS(create=self._create)
        self.calls = 0
        self.stop = stop

    def _create(self, **kw):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(reply, Exception):
            raise reply
        blocks = [NS(type="tool_use", id=f"t{self.calls}_{i}", name=n, input=a) for i, (n, a) in enumerate(reply)]
        return NS(content=blocks, stop_reason=self.stop, usage=NS(input_tokens=1, output_tokens=1))


def api_error():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError("credit balance is too low", response=httpx.Response(400, request=req), body=None)


def run(tmp_path, method="lidar_agent", client=None, **kw):
    return pipeline.run_pipeline(ADDR, tmp_path / method, method, blocks_path=BLOCKS, client=client, verify=False,
                                 render=False, **kw)


@pytest.fixture
def agent_wins(monkeypatch):
    """The agent is never worse than the rules in the test (the comparison itself is tested in test_agent_pick.py)."""
    monkeypatch.setattr(pipeline.agent_pick, "rules_if_not_worse", lambda *a, **k: None)


@pytest.fixture
def rules(tmp_path):
    """The rule result the fallback must equal."""
    return run(tmp_path / "rules", "lidar_skeleton")


def assert_is_rule_result(res, rules, cause_part):
    assert res.method_used == "lidar_skeleton" and res.envelope["method_used"] == "lidar_skeleton"
    assert res.envelope["totals"] == rules.envelope["totals"]
    assert res.model["source"]["method"] == "lidar_skeleton" and "agent" not in res.model["debug"]
    codes, warns = res.envelope["warning_codes"], res.envelope["warnings"]
    assert CODE in codes and len(codes) == len(warns)
    assert CODE in res.envelope["model"]["quality"]["reasons"]  # the quality block agrees with the warnings
    text = warns[codes.index(CODE)]
    assert cause_part in text and "\n" not in text and len(text) < 400


def test_the_code_is_a_known_warning_code():
    assert CODE in WARNING_CODES


# ----------------------------------------------------------------------------- each failure kind
def test_agent_error_from_the_api_falls_back(tmp_path, rules):
    res = run(tmp_path, client=Client(api_error()))
    assert_is_rule_result(res, rules, "credit balance is too low")


def test_agent_that_never_finalizes_falls_back(tmp_path, rules):
    res = run(tmp_path, client=Client([("measure", {"polygon_id": "footprint"})]), max_rounds=2)
    assert_is_rule_result(res, rules, "did not finalize within 2 rounds")


def test_truncated_turn_falls_back(tmp_path, rules):
    res = run(tmp_path, client=Client([("measure", {"polygon_id": "footprint"})], stop="max_tokens"))
    assert_is_rule_result(res, rules, "ran out of output tokens")


def test_shapely_error_in_the_agent_stage_falls_back(tmp_path, rules, monkeypatch):
    def boom(*a, **k):
        raise GEOSException("TopologyException: found non-noded intersection")

    monkeypatch.setattr(agent_mod, "run_agent", boom)
    res = run(tmp_path, client=Client([]))
    assert_is_rule_result(res, rules, "GEOSException")


def test_timeout_of_the_agent_stage_falls_back(tmp_path, rules, monkeypatch):
    def slow(*a, **k):
        raise DeadlineExceeded("agent")

    monkeypatch.setattr(agent_mod, "run_agent", slow)
    res = run(tmp_path, client=Client([]), deadline=Deadline.after(600))
    assert_is_rule_result(res, rules, "deadline exceeded during agent")


def test_agent_gets_a_share_of_the_time_so_the_rules_still_have_some(tmp_path, monkeypatch):
    seen = []
    real = agent_mod.run_agent

    def spy(*a, **k):
        seen.append(k["deadline"].remaining())
        return real(*a, **k)

    monkeypatch.setattr(agent_mod, "run_agent", spy)
    run(tmp_path, client=Client([("finalize", FLAT_FINAL)]), deadline=Deadline.after(100))
    assert 0 < seen[0] <= 100 * pipeline.AGENT_BUDGET_SHARE + 1


def test_blocks_the_model_rejects_fall_back(tmp_path, rules, monkeypatch):
    """The third blocker: finalize accepted blocks, build_model raised ModelError (a sliver facet)."""
    real = pipeline.build_model
    calls = []

    def build(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ModelError("facet f19 has a spike (6.5 deg)")
        return real(*a, **k)

    monkeypatch.setattr(pipeline, "build_model", build)
    res = run(tmp_path, client=Client([("finalize", FLAT_FINAL)]))
    assert len(calls) == 2
    assert_is_rule_result(res, rules, "ModelError: facet f19 has a spike")


def test_shapely_error_while_building_agent_blocks_falls_back(tmp_path, rules, monkeypatch):
    real = pipeline.build_model
    calls = []

    def build(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise GEOSException("boom")
        return real(*a, **k)

    monkeypatch.setattr(pipeline, "build_model", build)
    res = run(tmp_path, client=Client([("finalize", FLAT_FINAL)]))
    assert_is_rule_result(res, rules, "GEOSException")


# ----------------------------------------------------------------------------- what must NOT fall back
def test_a_working_agent_is_not_replaced_and_has_no_code(tmp_path, agent_wins):
    """Rewritten for 0.4.0: a flat-only answer is worse than the rule roof and is now replaced (test_agent_pick.py),
    so this test makes the agent win the comparison and checks that a winning agent is left alone."""
    res = run(tmp_path, client=Client([("finalize", FLAT_FINAL)]))
    assert res.method_used == "lidar_agent" and CODE not in res.envelope["warning_codes"]
    assert res.model["debug"]["agent"]["api_calls"] == 1 and res.agent_transcript is not None


def test_the_job_out_of_time_is_still_a_timeout_not_a_fallback(tmp_path, monkeypatch):
    def slow(*a, **k):
        raise DeadlineExceeded("agent")

    monkeypatch.setattr(agent_mod, "run_agent", slow)
    with pytest.raises(DeadlineExceeded):
        run(tmp_path, client=Client([]), deadline=Deadline.after(0.0))


def test_a_deadline_of_another_stage_is_raised(tmp_path, monkeypatch):
    def other(*a, **k):
        raise DeadlineExceeded("verify")

    monkeypatch.setattr(agent_mod, "run_agent", other)
    with pytest.raises(DeadlineExceeded):
        run(tmp_path, client=Client([]), deadline=Deadline.after(600))


@pytest.mark.parametrize("cls, status", [(anthropic.AuthenticationError, 401), (anthropic.PermissionDeniedError, 403)])
def test_a_rejected_key_is_raised_not_hidden_by_the_fallback(tmp_path, cls, status):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = cls("invalid x-api-key", response=httpx.Response(status, request=req), body=None)
    with pytest.raises(pipeline.PipelineError, match="API key was rejected") as e:
        run(tmp_path, client=Client(err))
    assert isinstance(e.value, agent_mod.AgentAuthError)
    from roof_measure.errors import error_from

    out = error_from(e.value)
    assert out["code"] == "measurement_failed" and not out["retryable"] and "API key was rejected" in out["message"]


def test_a_missing_api_key_is_still_a_caller_error(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(pipeline.PipelineError, match="needs an Anthropic API key"):
        run(tmp_path, client=None)


@pytest.mark.parametrize("exc", [RuntimeError("a bug in our code"), OverflowError("cannot convert float infinity"),
                                 KeyError("polygon"), IndexError("list index out of range")])
def test_any_exception_from_the_agent_path_falls_back(tmp_path, rules, monkeypatch, exc):
    """Rewritten: this test used to assert that a RuntimeError propagated. The agent is never a new way to fail."""
    def bug(*a, **k):
        raise exc

    monkeypatch.setattr(agent_mod, "run_agent", bug)
    res = run(tmp_path, client=Client([]))
    assert_is_rule_result(res, rules, type(exc).__name__)


def test_base_exceptions_are_not_swallowed(tmp_path, monkeypatch):
    def stop(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(agent_mod, "run_agent", stop)
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, client=Client([]))


def test_an_overflowing_finalize_is_handled_inside_the_loop_and_the_agent_still_wins(tmp_path, agent_wins):
    """The adversary's input: gable_edges [1e999, 0]. The loop tells the model; the next finalize is accepted."""
    bad = json.loads('{"blocks": [{"polygon_id": "footprint", "form": "gable", "pitch_rise": 4.0, '
                     '"gable_edges": [1e999, 0], "confidence": "low", "evidence": []}]}')
    res = run(tmp_path, client=Client([("finalize", bad)], [("finalize", FLAT_FINAL)]))
    assert res.method_used == "lidar_agent" and CODE not in res.envelope["warning_codes"]


@pytest.mark.parametrize("method", ["lidar_skeleton", "auto"])
def test_rule_methods_are_untouched_and_never_call_the_agent(tmp_path, monkeypatch, method):
    client = Client(api_error())
    monkeypatch.setattr(agent_mod, "run_agent", lambda *a, **k: pytest.fail("the agent must not run"))
    res = run(tmp_path, method, client=client)
    assert res.method_used == "lidar_skeleton" and CODE not in res.envelope["warning_codes"] and client.calls == 0


def test_a_rule_method_that_fails_in_the_model_returns_the_planes_and_without_planes_still_fails(tmp_path, monkeypatch):
    """Rewritten for 0.3.1: with LiDAR planes the model failure is no longer an error (planes_only.py)."""
    def build(*a, **k):
        raise ModelError("facet f1 has a spike")

    monkeypatch.setattr(pipeline, "build_model", build)
    res = run(tmp_path, "lidar_skeleton")
    assert res.envelope["model"]["source"]["planes_only"] and "model_failed" in res.envelope["warning_codes"]
    from roof_measure.classify import BlockSet

    bare = BlockSet.load(BLOCKS)
    bare.blocks = []  # no LiDAR plane at all: the error stays what it was
    bare.save(tmp_path / "bare.json")
    with pytest.raises(ModelError):
        pipeline.run_pipeline(ADDR, tmp_path / "bare", "lidar_skeleton", blocks_path=tmp_path / "bare.json",
                              verify=False, render=False)


def test_lidar_agent_without_agent_flag_is_the_old_deterministic_path(tmp_path, rules):
    res = run(tmp_path, no_agent=True)
    assert res.method_used == "lidar_agent" and CODE not in res.envelope["warning_codes"]


# ----------------------------------------------------------------------------- solar_agent
def test_solar_agent_failure_falls_back_to_the_rules_on_the_segments(tmp_path):
    kw = {"blocks_path": BLOCKS, "solar_fixture": SOLAR, "verify": False, "render": False}
    rules = pipeline.run_pipeline(ADDR, tmp_path / "r", "solar_agent", no_agent=True, **kw)
    res = pipeline.run_pipeline(ADDR, tmp_path / "a", "solar_agent", client=Client(api_error()), **kw)
    assert res.method_used == "solar_agent"  # there is no LiDAR to call it lidar_skeleton; the geometry is Solar
    assert res.envelope["totals"] == rules.envelope["totals"]
    codes = res.envelope["warning_codes"]
    assert CODE in codes and "solar_segments_only" in codes and "agent" not in res.model["debug"]


# ----------------------------------------------------------------------------- the child process dies
@pytest.fixture(autouse=False)
def hang_guard():
    def handler(signum, frame):
        raise TimeoutError("test hung")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(120)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.fixture
def first_child_crashes(monkeypatch, hang_guard):
    """The first child is the crashing test entry, every later one the real ``_child``."""
    started = []
    real_argv = isolate._child_argv

    def argv():
        started.append(1)
        return [sys.executable, "-P", str(ENTRY)] if len(started) == 1 else real_argv()

    monkeypatch.setattr(isolate, "_child_argv", argv)
    monkeypatch.setattr(roof_measure.library, "KILL_GRACE_S", 5.0)
    return started


@pytest.fixture
def first_child_hangs(monkeypatch, hang_guard):
    """The first child reports the model stage and then hangs like a native loop; the later ones are real."""
    started = []
    real_argv = isolate._child_argv

    def argv():
        started.append(1)
        return [sys.executable, "-P", str(ENTRY), "hang"] if len(started) == 1 else real_argv()

    monkeypatch.setattr(isolate, "_child_argv", argv)
    monkeypatch.setattr(roof_measure.library, "KILL_GRACE_S", 5.0)
    return started


def call(tmp_path, method, **kw):
    return measure(ADDR, method=method, verify=False, cache_dir=tmp_path / "cache", blocks_path=BLOCKS, **kw)


def test_a_crashed_lidar_agent_child_is_retried_as_lidar_skeleton(tmp_path, first_child_crashes):
    env = call(tmp_path, "lidar_agent")
    assert len(first_child_crashes) == 2
    assert env["method_used"] == "lidar_skeleton" and CODE in env["warning_codes"]
    assert len(env["warnings"]) == len(env["warning_codes"])
    text = env["warnings"][env["warning_codes"].index(CODE)]
    assert "SIGSEGV" in text and "exited with code -11" in text  # the crash cause is in the warning
    assert CODE in env["model"]["quality"]["reasons"]  # and in the quality reasons, like the in-process fallback
    assert env["totals"]["area_sqft"] > 0


def test_a_hang_in_the_agent_stage_falls_back_when_time_remains(tmp_path, first_child_hangs):
    env = call(tmp_path, "lidar_agent", deadline_s=60.0)
    assert len(first_child_hangs) == 2
    assert env["method_used"] == "lidar_skeleton" and CODE in env["warning_codes"]
    text = env["warnings"][env["warning_codes"].index(CODE)]
    assert "agent stage did not finish" in text and CODE in env["model"]["quality"]["reasons"]


def test_stages_are_not_reported_twice_across_a_retry(tmp_path, first_child_crashes):
    stages = []
    call(tmp_path, "lidar_agent", on_stage=stages.append)
    assert stages == ["model", "render"]  # the crashed child reported "model"; the retry does not repeat it


def test_stages_without_a_crash_are_unchanged(tmp_path):
    stages = []
    call(tmp_path, "lidar_skeleton", on_stage=stages.append)
    assert stages == ["model", "render"]


@pytest.mark.parametrize("method", ["lidar_skeleton", "solar_agent"])
def test_other_methods_are_not_retried_after_a_crash(tmp_path, first_child_crashes, method):
    kw = {"solar_fixture": SOLAR} if method == "solar_agent" else {}
    with pytest.raises(MeasureError, match="Segmentation fault"):
        call(tmp_path, method, **kw)
    assert len(first_child_crashes) == 1


@pytest.mark.parametrize("deadline_s", [5.0, 29.0])
def test_no_retry_when_too_little_time_is_left_and_the_crash_is_the_error(tmp_path, first_child_crashes, deadline_s):
    with pytest.raises(isolate.ChildCrashed, match="SIGSEGV"):
        call(tmp_path, "lidar_agent", deadline_s=deadline_s)
    assert len(first_child_crashes) == 1


def test_a_retry_that_times_out_does_not_hide_the_crash(tmp_path, first_child_crashes, monkeypatch):
    real = isolate.run_isolated
    seen = []

    def run_isolated(req, on_stage, grace):
        seen.append(req["method"])
        if len(seen) == 1:
            return real(req, on_stage, grace)
        raise MeasureError("timeout", "the measurement process was stopped after 30 s", retryable=True)

    monkeypatch.setattr(isolate, "run_isolated", run_isolated)
    with pytest.raises(isolate.ChildCrashed, match="SIGSEGV") as e:
        call(tmp_path, "lidar_agent")
    assert seen == ["lidar_agent", "lidar_skeleton"] and isinstance(e.value.__cause__, MeasureError)
    assert e.value.__cause__.code == "timeout"
