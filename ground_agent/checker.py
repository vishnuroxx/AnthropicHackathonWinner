"""Ground-side constraint checker (CLAUDE.md section 8). Pure code, no LLM.

Rules: C-GATE-1 gate free (waiting allowed up to MAX_GATE_WAIT_MIN), C-GATE-2 gate-change
notice, C-TURN-1 minimum turnaround (hard), C-CREW-1 crew overtime (soft: cost + flag).
`check_ground` is the entry point for the shared checker.py. Limits come from the workbook
(via WorldState); the wait cap is a labelled assumption (ground_agent/assumptions.py).
"""
from dataclasses import dataclass, field
from typing import Optional

from agents.schema import Plan
from ground_agent.assumptions import MAX_GATE_WAIT_MIN
from ground_agent.inputs import WorldState, walk_min
from ground_agent.timeutil import hhmm_to_min


@dataclass
class Violation:
    rule_id: str
    message: str
    values: dict


@dataclass
class Check:
    rule_id: str
    passed: bool
    detail: str
    values: dict


@dataclass
class GroundCheck:
    valid: bool
    violations: list[Violation]
    checks: list[Check]
    metrics: dict = field(default_factory=dict)

    # Serialises for prompts and the consensus log.
    # Returns: plain dict.
    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "violations": [vars(v) for v in self.violations],
            "checks": [vars(c) for c in self.checks],
            "metrics": self.metrics,
        }


# Parses an arrival slot, rolling past midnight when it is far before the reference time.
# Args: slot - "HH:MM"; ref_min - scheduled arrival in minutes.
# Returns: minutes from midnight, possibly > 1440.
def _slot_to_min(slot: str, ref_min: int) -> int:
    m = hhmm_to_min(slot)
    return m + 1440 if m < ref_min - 720 else m


# Earliest start >= arrival at which a gate stays free for `turnaround` minutes.
# Args: windows - the gate's busy windows; arrival - landing time; turnaround - occupancy minutes.
# Returns: start minute of the occupancy.
def _earliest_free_start(windows, arrival: int, turnaround: int) -> int:
    t = arrival
    for w in sorted(windows, key=lambda w: w.start):
        if t < w.end and t + turnaround > w.start:
            t = w.end
    return t


# Checks a plan against Ground's constraints and computes the Ground metrics used by cost.
# Args: plan - the plan under test; state - world state; turnaround_min - override for tests and
#   future use (the shared Plan has no turnaround field, so None means the airport minimum).
# Returns: GroundCheck (valid=False if any hard rule is violated).
def check_ground(plan: Plan, state: WorldState, turnaround_min: Optional[int] = None) -> GroundCheck:
    arrival = _slot_to_min(plan.arrival_slot, state.scheduled_arrival_min)
    turnaround = turnaround_min if turnaround_min is not None else state.limits.min_turnaround_min
    violations: list[Violation] = []
    checks: list[Check] = []
    flags: list[str] = []

    def hard(rule: str, ok: bool, ok_detail: str, bad_detail: str, values: dict) -> None:
        checks.append(Check(rule, ok, ok_detail if ok else bad_detail, values))
        if not ok:
            violations.append(Violation(rule, bad_detail, values))

    # C-TURN-1
    hard("C-TURN-1", turnaround >= state.limits.min_turnaround_min,
         f"turnaround {turnaround} min >= airport minimum {state.limits.min_turnaround_min}",
         f"turnaround {turnaround} min < airport minimum {state.limits.min_turnaround_min}",
         {"turnaround_min": turnaround, "minimum": state.limits.min_turnaround_min})

    # C-GATE-1
    gate_known = plan.gate in state.gate_busy
    wait = 0
    if gate_known:
        wait = _earliest_free_start(state.gate_busy[plan.gate], arrival, turnaround) - arrival
    hard("C-GATE-1", gate_known and wait <= MAX_GATE_WAIT_MIN,
         f"gate {plan.gate} free after {wait} min wait (cap {MAX_GATE_WAIT_MIN})",
         f"unknown gate {plan.gate}" if not gate_known
         else f"gate {plan.gate} not free within {MAX_GATE_WAIT_MIN} min of arrival (wait {wait})",
         {"gate": plan.gate, "gate_wait_min": wait, "cap": MAX_GATE_WAIT_MIN})

    # C-GATE-2
    changed = plan.gate != state.scheduled_gate
    notice = arrival - state.now_min
    hard("C-GATE-2", not changed or notice >= state.gate_change_notice_min,
         "gate unchanged" if not changed else f"gate change notice {notice} min >= {state.gate_change_notice_min}",
         f"gate change notice {notice} min < {state.gate_change_notice_min}",
         {"changed": changed, "notice_min": notice, "required": state.gate_change_notice_min})

    # C-CREW-1 (soft)
    occ_start = arrival + wait
    occ_end = occ_start + turnaround
    overtime = max(0, occ_end - state.crew_shift_end_min)
    if overtime:
        flags.append("CREW_OVERTIME")
    checks.append(Check("C-CREW-1", True,
                        f"crew overtime {overtime} min (soft cost)" if overtime else "within crew shift",
                        {"overtime_min": overtime, "shift_end_min": state.crew_shift_end_min}))

    # Knock-on to the next leg. The part present even in the best case (arrive at the disrupted
    # time, minimum turnaround) is the event's fault and identical across plans, so cost ignores it.
    knock_on = max(0, occ_end - state.next_departure_min)
    best_case_end = state.disrupted_arrival_min + state.limits.min_turnaround_min
    unavoidable = max(0, best_case_end - state.next_departure_min)

    walk = walk_min(state.scheduled_gate, plan.gate) if gate_known else 0
    missed = state.connecting_pax if changed and walk > state.connection_slack_min else 0
    if missed:
        flags.append("CONNECTION_RISK")
    metrics = {
        "gate_wait_min": wait, "turnaround_min": turnaround,
        "occupancy_start_min": occ_start, "occupancy_end_min": occ_end,
        "overtime_min": overtime,
        "knock_on_delay_min": knock_on,
        "avoidable_knock_on_min": max(0, knock_on - unavoidable),
        "gate_changed": changed, "walk_min": walk, "missed_connections": missed,
        "flags": flags,
    }
    return GroundCheck(not violations, violations, checks, metrics)
