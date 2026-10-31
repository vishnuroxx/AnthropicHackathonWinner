from agents.constraints import airport_limits, fuel_crew_rules
from agents.schema import Plan
from ground_agent.inputs import BusyWindow, WorldState
from ground_agent.timeutil import min_to_hhmm


# A small hand-built DFW state: arrival 20:00 (1200), gate A1 free, B2 busy to 20:20, no overtime.
# Limits, crew shift and gate-change notice come from the workbook, like the real builder.
def make_state(**over) -> WorldState:
    rules = fuel_crew_rules()
    shift = round(rules.ground_crew_shift_h * 60)
    kw = dict(
        seed=0, airport="DFW", limits=airport_limits()["DFW"], focal_flight="AA1", tail="N1",
        event_type="weather", event_magnitude_min=60, scheduled_arrival_min=1140, disrupted_arrival_min=1200,
        scheduled_gate="A1", now_min=1100, next_departure_min=1300, crew_shift_start_min=1200 - 60,
        connecting_pax=30, connection_slack_min=10,
        crew_shift_min=shift, gate_change_notice_min=round(rules.gate_change_notice_min),
        gate_busy={"A1": [], "A2": [], "B2": [BusyWindow(1150, 1220, "bg")], "C3": []},
    )
    kw.update(over)
    return WorldState(**kw)


# Builds a plan arriving at `slot` minutes from midnight at `gate`.
def plan(slot=1200, gate="A1") -> Plan:
    return Plan(arrival_slot=min_to_hhmm(slot), ground_delay_min=0, holding_min=0, extra_fuel_min=0,
                gate=gate, divert=False)
