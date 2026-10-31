"""Ground's option table: the verified alternatives the agent chooses from (LLM-Modulo: code
enumerates and checks, Claude picks and explains). Ground-side only: gate options at the airport
minimum turnaround (a longer turnaround only adds cost, so it is not enumerated).
"""
from dataclasses import dataclass

from agents.schema import Plan
from ground_agent.checker import GroundCheck, check_ground
from ground_agent.cost import cost_ground
from ground_agent.inputs import WorldState
from ground_agent.timeutil import min_to_hhmm


@dataclass
class Option:
    id: str
    gate: str
    plan: Plan
    check: GroundCheck
    cost: dict

    # An option is selectable only if it passes every hard Ground rule.
    # Returns: True if the Ground check is valid.
    @property
    def selectable(self) -> bool:
        return self.check.valid


# Free gates for the focal flight: no busy window between the announcement and 4 h after the
# disrupted arrival (excludes the scheduled gate). Natural gate order (A2 before A10).
# Args: state - world state.
# Returns: list of gate ids.
def free_gate_ids(state: WorldState) -> list[str]:
    horizon_end = state.disrupted_arrival_min + 240
    free = [
        g for g, w in state.gate_busy.items()
        if g != state.scheduled_gate and not any(x.start < horizon_end and x.end > state.now_min for x in w)
    ]
    return sorted(free, key=lambda g: (g[0], int(g[1:])))


# Enumerates the Ground options at a given arrival time: scheduled gate first, then each free gate.
# Args: state - world state; arrival_min - arrival time in minutes from midnight.
# Returns: list of Option with ids G1, G2, ...
def enumerate_options(state: WorldState, arrival_min: int) -> list[Option]:
    options = []
    for i, gate in enumerate([state.scheduled_gate] + free_gate_ids(state), start=1):
        plan = Plan(arrival_slot=min_to_hhmm(arrival_min), ground_delay_min=0, holding_min=0,
                    extra_fuel_min=0, gate=gate, divert=False)
        check = check_ground(plan, state)
        options.append(Option(f"G{i}", gate, plan, check, cost_ground(check)))
    return options


# The Ground-side baseline and BATNA: the cheapest option that passes every hard rule.
# Args: options - result of enumerate_options.
# Returns: the cheapest selectable Option (ties by id), or None if none is valid.
def cheapest_valid(options: list[Option]):
    return min((o for o in options if o.selectable), key=lambda o: (o.cost["total"], o.id), default=None)


# Selectable options ranked cheapest first, in the shape of the shared ICAP `alternatives`.
# Args: options - result of enumerate_options.
# Returns: list of {"plan_ref", "summary", "status"} (all "candidate": ATC has not confirmed the slot).
def ranked_alternatives(options: list[Option]) -> list[dict]:
    valid = sorted((o for o in options if o.selectable), key=lambda o: (o.cost["total"], o.id))
    return [
        {"plan_ref": o.id, "status": "candidate",
         "summary": (f"gate {o.gate}: wait {o.check.metrics['gate_wait_min']} min, overtime "
                     f"{o.check.metrics['overtime_min']} min, ready {min_to_hhmm(o.check.metrics['ready_time_min'])}, "
                     f"cost ${o.cost['total']:.0f}")}
        for o in valid
    ]
