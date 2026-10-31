"""Enumerate recovery plans, check hard rules, cost them, pick the cheapest valid one. Deterministic.

Candidates: slots (5-min grid, earliest arrival to +3 h) x {ground delay | holding + extra fuel} x gates,
plus one diversion. Also the evaluation baseline (trigger "baseline").
"""
import math
from collections import Counter

from . import config
from .rules import check, divert_flight_min, landing_stream
from .world import FallbackWorld

TIE_BREAK = ["cost_usd", "total_system_delay_min", "holding_min", "divert", "arrival_slot", "gate"]


def _hhmm(m: int) -> str:
    return f"{m % 1440 // 60:02d}:{m % 60:02d}"


# Candidate plans in a fixed order: (slot minute, plan dict).
def _enumerate(world: FallbackWorld) -> list[tuple[int, dict]]:
    out = []
    for slot in range(world.earliest_arr_min, world.earliest_arr_min + config.HORIZON_MIN + 1, config.SLOT_MIN):
        wait = slot - world.earliest_arr_min
        levers = [(wait, 0, 0)] + ([(0, wait, x) for x in config.EXTRA_FUEL_OPTIONS] if wait > 0 else [])
        for ground, hold, extra in levers:
            for gate in world.gates:
                out.append((slot, {"arrival_slot": _hhmm(slot), "ground_delay_min": ground, "holding_min": hold,
                                   "extra_fuel_min": extra, "gate": gate, "divert": False}))
    alt_slot = world.earliest_arr_min + math.ceil(divert_flight_min(world))
    out.append((alt_slot, {"arrival_slot": _hhmm(alt_slot), "ground_delay_min": 0, "holding_min": 0,
                           "extra_fuel_min": 0, "gate": None, "divert": True}))
    return out


# Costs a checked plan in USD (total system cost incl. knock-on to re-sequenced background flights).
# Returns: (cost_usd, total_system_delay_min, breakdown).
def _cost(plan: dict, slot: int, chk: dict, world: FallbackWorld) -> tuple[float, int, dict]:
    soft = chk["soft"]
    knock = 0
    if not plan["divert"]:
        base, with_focal = landing_stream(world, None), landing_stream(world, slot)
        knock = round(sum(max(0.0, with_focal[k] - base[k]) for k in base))
    parts = {
        "ground_delay": plan["ground_delay_min"] * config.GROUND_DELAY_PER_MIN,
        "holding": plan["holding_min"] * config.HOLDING_PER_MIN,
        "extra_fuel": plan["extra_fuel_min"] * config.EXTRA_FUEL_PER_MIN,
        "gate_change": config.GATE_CHANGE_FIXED if not plan["divert"] and plan["gate"] != world.scheduled_gate else 0,
        "crew_overtime": soft["crew_overtime_min"] * config.CREW_BASE_PER_MIN * config.CREW_OVERTIME_MULT,
        "next_leg_delay": soft["next_leg_delay_min"] * config.NEXT_LEG_PER_MIN,
        "missed_connections": soft["missed_pax"] * config.MISSED_CONNECTION_PER_PAX,
        "knock_on_background": knock * config.KNOCK_ON_BG_PER_MIN,
        "diversion": config.DIVERT_FIXED if plan["divert"] else 0,
    }
    parts = {k: round(v, 2) for k, v in parts.items()}
    return round(sum(parts.values()), 2), slot - world.sched_arr_min + knock, parts


# Least-cost valid plan, or a cancellation recommendation when no plan passes every hard rule.
# Args: world - FallbackWorld; trigger - why the fallback runs (config.TRIGGERS).
# Returns: JSON-serialisable dict, identical across runs for the same world.
def solve(world: FallbackWorld, trigger: str) -> dict:
    scored, rejected = [], Counter()
    cands = _enumerate(world)
    for n, (slot, plan) in enumerate(cands, 1):
        chk = check(plan, world)
        if not chk["valid"]:
            rejected.update(v.split(":")[0] for v in chk["violations"])
            continue
        cost, delay, parts = _cost(plan, slot, chk, world)
        key = (cost, delay, plan["holding_min"], plan["divert"], slot, plan["gate"] or "")
        scored.append((key, f"F{n}", plan, chk, cost, delay, parts))
    scored.sort(key=lambda s: s[0])
    info = {"trigger": trigger, "candidates_enumerated": len(cands), "valid": len(scored),
            "tie_break": TIE_BREAK, "rejected_by_rule": dict(sorted(rejected.items()))}
    if not scored:
        return {"outcome": "recommend_cancel", "proposed_by": "fallback", "plan": None, "check": None,
                "cost_usd": config.CANCEL_COST, "total_system_delay_min": None,
                "fallback": info | {"selected_source_id": None, "runner_up": None,
                                    "note": "no valid plan: recommendation to the human, never auto-applied"}}
    _, sid, plan, chk, cost, delay, parts = scored[0]
    runner = None
    if len(scored) > 1:
        runner = {"source_id": scored[1][1], "plan": scored[1][2], "cost_usd": scored[1][4],
                  "total_system_delay_min": scored[1][5]}
    return {"outcome": "halt_least_cost", "proposed_by": "fallback", "plan": plan, "check": chk,
            "cost_usd": cost, "total_system_delay_min": delay,
            "fallback": info | {"selected_source_id": sid, "runner_up": runner, "cost_breakdown": parts}}
