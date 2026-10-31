from ground_agent.inputs import BusyWindow
from ground_agent.options import cheapest_valid, enumerate_options, free_gate_ids, ranked_alternatives
from ground_agent.tests.helpers import make_state


def test_options_start_with_scheduled_gate_then_free_gates():
    s = make_state()
    opts = enumerate_options(s, s.disrupted_arrival_min)
    assert [(o.id, o.gate) for o in opts] == [("G1", "A1"), ("G2", "A2"), ("G3", "C3")]  # B2 is busy
    assert free_gate_ids(s) == ["A2", "C3"]


def test_cheapest_valid_is_the_minimum_cost_valid_option():
    s = make_state()
    opts = enumerate_options(s, s.disrupted_arrival_min)
    best = cheapest_valid(opts)
    assert best.id == "G1" and best.cost["total"] == min(o.cost["total"] for o in opts if o.selectable)


def test_invalid_option_is_unselectable_and_excluded_from_ranking():
    s = make_state(gate_busy={"A1": [BusyWindow(1190, 1300, "bg")], "A2": [], "C3": []})
    opts = enumerate_options(s, s.disrupted_arrival_min)
    g1 = opts[0]
    assert not g1.selectable and [v.rule_id for v in g1.check.violations] == ["C-GATE-1"]
    assert cheapest_valid(opts).id == "G2"
    assert "G1" not in [a["plan_ref"] for a in ranked_alternatives(opts)]


def test_no_valid_option_gives_no_baseline():
    s = make_state(gate_busy={"A1": [BusyWindow(1190, 1300, "bg")]})
    # only the scheduled gate exists, and it is not free within the wait cap
    assert cheapest_valid(enumerate_options(s, s.disrupted_arrival_min)) is None


def test_ranked_alternatives_are_cheapest_first_candidates():
    s = make_state()
    ranked = ranked_alternatives(enumerate_options(s, s.disrupted_arrival_min))
    assert [a["plan_ref"] for a in ranked] == ["G1", "G2", "G3"]
    assert all(a["status"] == "candidate" and a["summary"] for a in ranked)
