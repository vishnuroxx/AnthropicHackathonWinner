import asyncio
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from agents.ground import GroundAgent, GroundDecision, assert_no_hindsight, baseline_plan, build_ground_facts
from checker_ground import check_ground
from tests.test_checker_ground import make_state


# Builds a GroundDecision with sensible defaults.
def decision(**over) -> GroundDecision:
    kw = dict(action="propose", plan_id=None, gate="A1", turnaround_min=45, need="n", offer="o",
              reason="C-GATE-1 gate free", flags=[])
    kw.update(over)
    return GroundDecision(**kw)


# Wraps a decision (or exception) as a fake messages.parse result.
def resp(d, stop="end_turn"):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(parsed_output=d, stop_reason=stop, usage=usage, _request_id="req_x")


class FakeClient:
    # Args: script - list of responses or exceptions returned by successive parse calls.
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = self

    async def parse(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run(coro):
    return asyncio.run(coro)


def test_propose_builds_full_plan_from_ground_levers():
    s = make_state()
    agent = GroundAgent(FakeClient([resp(decision(gate="A2", turnaround_min=50))]))
    m = run(agent.propose(s))
    assert m.from_ == "ground" and m.action == "propose" and m.round == 1
    base = baseline_plan(s)
    assert (m.plan.gate, m.plan.turnaround_min) == ("A2", 50)
    assert (m.plan.arrival_slot, m.plan.holding_min, m.plan.divert) == (base.arrival_slot, 0, False)


def test_invalid_then_valid_reasks_once():
    client = FakeClient([resp(decision(action="accept")), resp(decision())])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "propose" and len(client.calls) == 2
    assert "invalid" in client.calls[1]["messages"][-1]["content"]


def test_invalid_twice_becomes_reject():
    client = FakeClient([resp(decision(action="accept")), resp(decision(action="accept"))])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "reject" and len(client.calls) == 2


def test_word_limit_violation_is_reasked():
    with pytest.raises(ValidationError):
        decision(reason="word " * 31)
    try:
        decision(reason="word " * 31)
    except ValidationError as e:
        client = FakeClient([e, resp(decision())])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "propose" and len(client.calls) == 2


def test_cannot_accept_invalid_plan():
    s = make_state()
    bad = baseline_plan(s).model_copy(update={"gate": "Z99"})
    chk = check_ground(bad, s)
    assert not chk.valid
    client = FakeClient([resp(decision(action="accept", plan_id="P1")), resp(decision(action="accept", plan_id="P1"))])
    m = run(GroundAgent(client).respond(s, 2, "P1", bad, chk, []))
    assert m.action == "reject"


def test_accept_carries_table_plan_and_id():
    s = make_state()
    table = baseline_plan(s)
    m = run(GroundAgent(FakeClient([resp(decision(action="accept", plan_id="P1"))])).respond(
        s, 2, "P1", table, check_ground(table, s), []))
    assert (m.action, m.plan_id, m.plan) == ("accept", "P1", table)


def test_refusal_and_api_error_become_reject():
    s = make_state()
    assert run(GroundAgent(FakeClient([resp(None, stop="refusal")])).propose(s)).action == "reject"
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
    assert run(GroundAgent(FakeClient([err])).propose(s)).action == "reject"


def test_system_prompt_has_ground_facts_only_and_cache_breakpoint():
    client = FakeClient([resp(decision())])
    run(GroundAgent(client).propose(make_state()))
    system = client.calls[0]["system"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
    assert "FACTS" in system[-1]["text"]
    assert client.calls[0]["max_tokens"] > 0


def test_hindsight_guard():
    assert_no_hindsight(build_ground_facts(make_state()))
    with pytest.raises(ValueError):
        assert_no_hindsight({"focal_flight": {"ARRIVAL_DELAY": 5}})
