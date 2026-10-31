import json

from ground_agent.acdm import acdm_flags
from ground_agent.agent import assert_no_hindsight
from ground_agent.assumptions import ACDM_SOURCE
from ground_agent.checker import check_ground
from ground_agent.cost import cost_ground
from ground_agent.icap import build_icap
from ground_agent.inputs import BusyWindow
from ground_agent.tests.helpers import make_state, plan


def test_icap_is_deterministic_and_has_no_outcome_fields():
    s = make_state()
    a, b = build_icap(s), build_icap(s)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert_no_hindsight(a)


def test_constraint_values_come_from_the_state_not_retyped():
    c = build_icap(make_state())["constraints"]
    rule = {x["id"]: x["rule"] for x in c["hard"]}
    assert "20 min notice" in rule["C-GATE-2"] and "45 min" in rule["C-TURN-1"]
    assert "480 min" in c["soft"][0]["rule"]


def test_seven_interests_with_ids_in_order():
    ids = [i["id"] for i in build_icap(make_state())["interests"]]
    assert ids == ["I1", "I2", "I3", "I4", "I5", "I6", "I7"]


def test_priorities_ranked_by_stake_and_reproducible():
    ranked = build_icap(make_state())["priorities"]["ranked"]
    # stakes across valid options: connections 6000 (C3 gate change), gate change 400, the rest 0
    assert [(r["id"], r["stake_usd"]) for r in ranked[:2]] == [("I5", 6000.0), ("I7", 400.0)]
    assert [r["id"] for r in ranked] == ["I5", "I7", "I1", "I2", "I3", "I4", "I6"]
    assert ranked[-1]["stake_usd"] is None  # I6 is unpriced and goes last


def test_overtime_mismatch_note_appears_when_overtime_ranks_low():
    notes = build_icap(make_state())["notes"]
    assert any("avoid ground-crew overtime" in n and "ranks 6 of 7" in n for n in notes)
    assert not any("turnaround delays" in n or "gate utilisation" in n for n in notes)


def test_batna_is_the_cheapest_valid_option():
    batna = build_icap(make_state())["alternatives"]["batna"]
    assert (batna["option_id"], batna["gate"], batna["cost_usd"]) == ("G1", "A1", 0.0)


def test_no_valid_option_means_no_batna_and_a_note():
    s = make_state(gate_busy={"A1": [BusyWindow(1190, 1300, "bg")]})
    icap = build_icap(s)
    assert icap["alternatives"]["batna"] is None
    assert any("no BATNA" in n for n in icap["notes"])


def test_acdm_flag_boundaries_are_strictly_greater_than():
    assert acdm_flags(105, 100, 1000) == []  # moved exactly 5 min: no flag
    assert [f["flag"] for f in acdm_flags(106, 100, 1000)] == ["READY_TIME_UPDATE"]
    assert [f["flag"] for f in acdm_flags(94, 100, 1000)] == ["READY_TIME_UPDATE"]  # either direction
    assert acdm_flags(100, 100, 85) == []  # exactly 15 min past the next departure: no flag
    assert [f["flag"] for f in acdm_flags(100, 100, 84)] == ["DELAY_MESSAGE"]
    assert all(f["source"] == ACDM_SOURCE and "unverified" in f["source"] for f in acdm_flags(200, 100, 100))


def test_acdm_flags_never_change_validity_or_cost():
    s = make_state()
    base = check_ground(plan(), s, previous_ready_min=1245)  # same ready time as the plan: no update flag
    shifted = check_ground(plan(), s, previous_ready_min=1000)  # large shift: flag raised
    assert base.metrics["acdm_flags"] == [] and shifted.metrics["acdm_flags"]
    assert base.valid == shifted.valid and cost_ground(base) == cost_ground(shifted)


def test_ready_time_and_turnaround_delay_metrics():
    s = make_state(gate_busy={"A1": [BusyWindow(1190, 1215, "bg")]})  # 15 min wait for the gate
    m = check_ground(plan(), s).metrics
    assert m["gate_wait_min"] == 15 and m["turnaround_delay_min"] == 15
    assert m["ready_time_min"] == 1200 + 15 + 45
    # a longer turnaround than the minimum (future use) also counts as turnaround delay
    assert check_ground(plan(), make_state(), turnaround_min=60).metrics["turnaround_delay_min"] == 15
