import asyncio
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from agents.schema import validate_ranges
from ground_agent.agent import GroundAgent, GroundDecision, assert_no_hindsight, baseline_plan, build_ground_facts
from ground_agent.checker import check_ground
from ground_agent.tests.helpers import make_state


# Builds a GroundDecision with sensible defaults.
def decision(**over) -> GroundDecision:
    kw = dict(action="propose", plan_id=None, gate="A1", interests_cited=["I1"], need="n", offer="o",
              reason="C-GATE-1 gate free", requested_next_action="ATC: confirm slot")
    kw.update(over)
    return GroundDecision(**kw)


# Wraps a decision (or None) as a fake messages.parse result.
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


def test_propose_builds_full_plan_from_the_gate():
    s = make_state()
    agent = GroundAgent(FakeClient([resp(decision(gate="A2"))]))
    m = run(agent.propose(s))
    assert m.from_ == "ground" and m.action == "propose" and m.round == 1
    base = baseline_plan(s)
    assert m.plan.gate == "A2"
    assert (m.plan.arrival_slot, m.plan.holding_min, m.plan.divert) == (base.arrival_slot, 0, False)


def test_message_is_shared_schema_valid_with_icap():
    m = run(GroundAgent(FakeClient([resp(decision())])).propose(make_state()))
    assert validate_ranges(m) == []
    assert m.icap is not None and m.icap.interest and m.icap.requested_next_action == "ATC: confirm slot"
    assert m.icap.deadline and m.icap.concessions


def test_flags_are_derived_from_the_checker_not_the_model():
    s = make_state(crew_shift_start_min=1200 + 45 - 480 - 20)  # forces crew overtime at gate A1
    m = run(GroundAgent(FakeClient([resp(decision())])).propose(s))
    assert m.flags == ["CREW_OVERTIME"]


def test_invalid_then_valid_reasks_once():
    client = FakeClient([resp(decision(action="accept")), resp(decision())])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "propose" and len(client.calls) == 2
    assert "invalid" in client.calls[1]["messages"][-1]["content"]


def test_invalid_twice_becomes_reject():
    client = FakeClient([resp(decision(action="accept")), resp(decision(action="accept"))])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "reject" and len(client.calls) == 2 and m.icap is not None


def test_overlong_text_is_reasked_via_validate_ranges():
    client = FakeClient([resp(decision(need="word " * 40)), resp(decision())])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "propose" and len(client.calls) == 2
    assert "Fix these problems" in client.calls[1]["messages"][-1]["content"]


def test_schema_error_is_reasked():
    with pytest.raises(ValidationError):
        GroundDecision.model_validate({})
    try:
        GroundDecision.model_validate({})
    except ValidationError as e:
        client = FakeClient([e, resp(decision())])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "propose" and len(client.calls) == 2


def test_accept_of_invalid_plan_is_overridden_to_reject():
    s = make_state()
    bad = baseline_plan(s).model_copy(update={"gate": "Z99"})
    chk = check_ground(bad, s)
    assert not chk.valid
    client = FakeClient([resp(decision(action="accept", plan_id="P1"))])
    m = run(GroundAgent(client).respond(s, 2, "P1", bad, chk, []))
    assert m.action == "reject" and len(client.calls) == 1
    assert m.reason.startswith("Code override")
    assert m.icap.failed_constraint.rule == "gate" and "C-GATE-1" in m.icap.failed_constraint.evidence[0]


def test_accept_of_off_table_plan_id_is_overridden_to_reject():
    s = make_state()
    table = baseline_plan(s)
    client = FakeClient([resp(decision(action="accept", plan_id="P9"))])
    m = run(GroundAgent(client).respond(s, 2, "P1", table, check_ground(table, s), []))
    assert m.action == "reject" and "not the plan on the table" in m.reason


def test_accept_carries_table_plan_and_id():
    s = make_state()
    table = baseline_plan(s)
    m = run(GroundAgent(FakeClient([resp(decision(action="accept", plan_id="P1"))])).respond(
        s, 2, "P1", table, check_ground(table, s), []))
    assert (m.action, m.plan_id, m.plan) == ("accept", "P1", table)


def test_counter_against_invalid_table_plan_records_failed_constraint():
    s = make_state()
    bad = baseline_plan(s).model_copy(update={"gate": "Z99"})
    m = run(GroundAgent(FakeClient([resp(decision(action="counter", gate="A2"))])).respond(
        s, 2, "P1", bad, check_ground(bad, s), []))
    assert m.action == "counter" and m.plan.gate == "A2"
    assert m.icap.failed_constraint is not None and m.icap.failed_constraint.rule == "gate"


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


def test_unknown_interest_id_is_reasked():
    client = FakeClient([resp(decision(interests_cited=["I9"])), resp(decision())])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "propose" and len(client.calls) == 2
    assert "unknown interest ids" in client.calls[1]["messages"][-1]["content"]


def test_missing_interest_citation_is_reasked_then_rejected():
    client = FakeClient([resp(decision(interests_cited=[])), resp(decision(interests_cited=[]))])
    m = run(GroundAgent(client).propose(make_state()))
    assert m.action == "reject" and len(client.calls) == 2


def test_icap_brief_carries_cited_interests_and_code_alternatives():
    m = run(GroundAgent(FakeClient([resp(decision(interests_cited=["I1", "I4"]))])).propose(make_state()))
    assert m.icap.interest.endswith("[cites I1, I4]")
    assert [a.plan_ref for a in m.icap.alternatives] == ["G1", "G2", "G3"]  # cheapest valid first
    assert all(a.status == "candidate" for a in m.icap.alternatives)


def test_respond_payload_has_batna_gap_and_ready_time():
    s = make_state()
    table = baseline_plan(s).model_copy(update={"gate": "C3"})  # the costly option
    client = FakeClient([resp(decision(action="counter", gate="A1"))])
    run(GroundAgent(client).respond(s, 2, "P1", table, check_ground(table, s), []))
    user = client.calls[0]["messages"][0]["content"]
    assert '"vs_batna_usd": 6400.0' in user and '"ready_time": "20:45"' in user


def test_facts_include_icap_and_stay_deterministic():
    s = make_state()
    a, b = build_ground_facts(s), build_ground_facts(s)
    assert a["icap"]["priorities"]["ranked"][0]["id"] == "I5"
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)  # keeps the prompt cache valid


def test_hindsight_guard():
    assert_no_hindsight(build_ground_facts(make_state()))
    with pytest.raises(ValueError):
        assert_no_hindsight({"focal_flight": {"ARRIVAL_DELAY": 5}})
