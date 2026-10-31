from checker_ground import check_ground
from cost_ground import cost_ground
from limits import load_airport_limits
from schema import Plan, min_to_hhmm
from world_fixture import BusyWindow, WorldState, build_world


# A small hand-built DFW state: arrival 20:00 (1200), gate A1 free, B2 busy to 20:20, no overtime.
def make_state(**over) -> WorldState:
    kw = dict(
        seed=0, airport="DFW", limits=load_airport_limits("DFW"), focal_flight="AA1", tail="N1",
        event_type="weather", event_magnitude_min=60, scheduled_arrival_min=1140, disrupted_arrival_min=1200,
        scheduled_gate="A1", now_min=1100, next_departure_min=1300, crew_shift_start_min=1200 - 60,
        connecting_pax=30, connection_slack_min=10,
        gate_busy={"A1": [], "A2": [], "B2": [BusyWindow(1150, 1220, "bg")], "C3": []},
    )
    kw.update(over)
    return WorldState(**kw)


# Builds a plan arriving at `slot` minutes from midnight at `gate`.
def plan(slot=1200, gate="A1", turnaround=None) -> Plan:
    return Plan(arrival_slot=min_to_hhmm(slot), ground_delay_min=0, holding_min=0, extra_fuel_min=0,
                gate=gate, divert=False, turnaround_min=turnaround)


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
