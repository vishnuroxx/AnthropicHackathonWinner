from ground_agent.checker import check_ground
from ground_agent.cost import cost_ground
from ground_agent.tests.helpers import make_state, plan
from shared.limits import load_airport_limits
from shared.world_fixture import BusyWindow, build_world


def rules(check):
    return {v.rule_id for v in check.violations}


def test_workbook_limits_dfw():
    lim = load_airport_limits("DFW")
    assert (lim.gates, lim.min_turnaround_min, lim.spare_gates) == (150, 45, 3)


def test_valid_plan():
    c = check_ground(plan(), make_state())
    assert c.valid and c.metrics["gate_wait_min"] == 0 and c.metrics["overtime_min"] == 0


def test_gate_busy_beyond_wait_cap_is_c_gate_1():
    s = make_state(gate_busy={"A1": [BusyWindow(1190, 1300, "bg")]})
    assert rules(check_ground(plan(), s)) == {"C-GATE-1"}


def test_short_wait_is_cost_not_violation():
    s = make_state(gate_busy={"A1": [BusyWindow(1190, 1215, "bg")]})
    c = check_ground(plan(), s)
    assert c.valid and c.metrics["gate_wait_min"] == 15
    assert cost_ground(c)["items"]["gate_wait"] == 15 * 69.0


def test_unknown_gate_is_c_gate_1():
    assert rules(check_ground(plan(gate="Z99"), make_state())) == {"C-GATE-1"}


def test_gate_change_late_notice_is_c_gate_2():
    s = make_state(now_min=1190)  # 10 min notice < 20
    assert rules(check_ground(plan(gate="A2"), s)) == {"C-GATE-2"}
    assert check_ground(plan(gate="A1"), s).valid


def test_short_turnaround_is_c_turn_1():
    assert rules(check_ground(plan(turnaround=30), make_state())) == {"C-TURN-1"}


def test_overtime_is_soft():
    s = make_state(crew_shift_start_min=1200 + 45 - 480 - 20)  # shift ends 20 min before occupancy ends
    c = check_ground(plan(), s)
    assert c.valid and c.metrics["overtime_min"] == 20 and "CREW_OVERTIME" in c.metrics["flags"]
    assert cost_ground(c)["items"]["crew_overtime"] == 20 * 3.5 * 1.5


def test_other_terminal_gate_change_risks_connections():
    c = check_ground(plan(gate="C3"), make_state())  # walk 15 > slack 10
    assert c.valid and c.metrics["missed_connections"] == 30
    assert cost_ground(c)["items"]["missed_connections"] == 6000.0


def test_demo_world_builds_from_real_row():
    s = build_world()
    assert (s.focal_flight, s.airport, s.event_type, s.event_magnitude_min) == ("AA1480", "DFW", "weather", 165)
    assert sum(1 for w in s.gate_busy.values() if not w) == 3  # spare gates from the workbook
