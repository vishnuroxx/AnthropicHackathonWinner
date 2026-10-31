"""Ground's ICAP (Interests, Constraints, Alternatives, Priorities), built by code per scenario.

Code computes every number; the agent reads this block (in its FACTS) and fills the team's shared
`ICAPBrief`. Priorities are derived from the cost weights, so the ranking is reproducible, and
`notes` shows where the brief's stated Ground objectives land under those weights.
"""
from ground_agent import cost_config as C
from ground_agent.assumptions import (
    ACDM_DELAY_MESSAGE_MIN, ACDM_READY_UPDATE_MIN, ACDM_SOURCE, LOW_RANK_FROM,
    MAX_GATE_WAIT_MIN, OVERTIME_MULTIPLIER,
)
from ground_agent.inputs import WorldState
from ground_agent.options import cheapest_valid, enumerate_options, ranked_alternatives
from ground_agent.timeutil import min_to_hhmm

# The brief: "Ground: optimise gate utilisation, avoid ground-crew overtime, minimise turnaround delays."
STATED_OBJECTIVES = {
    "optimise gate utilisation": ["I1", "I6"],
    "avoid ground-crew overtime": ["I4"],
    "minimise turnaround delays": ["I2"],
}


# Static definition of the seven Ground interests: id, name, check metric, price (from cost_config).
# Returns: list of interest dicts in id order.
def _interest_defs() -> list[dict]:
    return [
        {"id": "I1", "name": "Gate wait: no aircraft idling for a gate", "measure": "gate_wait_min",
         "price": f"${C.GROUND_DELAY_PER_MIN + C.PAX_ONBOARD_PENALTY_PER_MIN:g} per min"},
        {"id": "I2", "name": "Minimise turnaround delay", "measure": "turnaround_delay_min",
         "price": "priced through I1 and I3 (composite, no double count)", "composite_of": ["I1", "I3"]},
        {"id": "I3", "name": "Protect the next leg", "measure": "avoidable_knock_on_min",
         "price": f"${C.KNOCK_ON_PER_MIN:g} per min"},
        {"id": "I4", "name": "No crew overtime", "measure": "overtime_min",
         "price": f"${C.CREW_BASE_PER_MIN * OVERTIME_MULTIPLIER:g} per min ({OVERTIME_MULTIPLIER}x)"},
        {"id": "I5", "name": "Protect connections on a gate change", "measure": "missed_connections",
         "price": f"${C.MISSED_CONNECTION_PER_PAX:g} per passenger"},
        {"id": "I6", "name": "Keep the spare gates available", "measure": "spare gates used",
         "price": "unpriced (tie-break only)"},
        {"id": "I7", "name": "Predictability: few gate changes", "measure": "gate_changed",
         "price": f"${C.GATE_CHANGE_FIXED:g} per change"},
    ]


# Builds Ground's ICAP for the disrupted arrival.
# Args: state - world state.
# Returns: JSON-serialisable dict: interests, constraints, alternatives (options, ranked, BATNA),
#   priorities (ranked by stake), notes, acdm.
def build_icap(state: WorldState) -> dict:
    options = enumerate_options(state, state.disrupted_arrival_min)
    valid = [o for o in options if o.selectable]
    item = lambda o, k: o.cost["items"][k]  # noqa: E731
    series = {
        "I1": lambda o: item(o, "gate_wait"),
        "I2": lambda o: item(o, "gate_wait") + item(o, "knock_on_delay"),
        "I3": lambda o: item(o, "knock_on_delay"),
        "I4": lambda o: item(o, "crew_overtime"),
        "I5": lambda o: item(o, "missed_connections"),
        "I7": lambda o: item(o, "gate_change"),
    }
    # Stake = how much this interest's dollar cost varies across the valid options.
    stake = {k: (round(max(f(o) for o in valid) - min(f(o) for o in valid), 2) if valid else 0.0)
             for k, f in series.items()}
    order = [d["id"] for d in _interest_defs()]
    ranked_ids = sorted(series, key=lambda k: (-stake[k], order.index(k))) + ["I6"]
    names = {d["id"]: d["name"] for d in _interest_defs()}
    ranked = [{"rank": i, "id": k, "name": names[k], "stake_usd": stake.get(k)}
              for i, k in enumerate(ranked_ids, start=1)]
    rank_of = {r["id"]: r["rank"] for r in ranked}

    notes = []
    for objective, ids in STATED_OBJECTIVES.items():
        best = min(rank_of[i] for i in ids)
        if best > LOW_RANK_FROM:
            notes.append(f"'{objective}' ranks {best} of {len(ranked)} under the current cost weights; "
                         "the brief lists it as a Ground objective")
    if not valid:
        notes.append("No Ground option passes every hard rule at the disrupted arrival; there is no BATNA")

    best = cheapest_valid(options)
    return {
        "interests": _interest_defs(),
        "constraints": {
            "hard": [
                {"id": "C-GATE-1", "rule": f"gate free for the whole occupancy; waiting up to {MAX_GATE_WAIT_MIN} min "
                 "is allowed", "source": "wait cap: team assumption"},
                {"id": "C-GATE-2", "rule": f"a gate change needs {state.gate_change_notice_min} min notice before arrival",
                 "source": "organiser workbook"},
                {"id": "C-TURN-1", "rule": f"turnaround at least {state.limits.min_turnaround_min} min",
                 "source": "organiser workbook (synthetic)"},
            ],
            "soft": [{"id": "C-CREW-1", "rule": f"crew shift {state.crew_shift_min} min; overtime costs "
                      f"{OVERTIME_MULTIPLIER}x and is flagged", "source": "organiser workbook"}],
            "blind_spots": ["ATC slot grid", "Pilot fuel state", "outcome columns",
                            "taxi/ramp-flow effect of a gate change (ATC concern, out of MVP scope)"],
        },
        "alternatives": {
            "levers": ["keep the scheduled gate and wait for it", "change to a free gate",
                       "longer turnaround (not enumerated: it only adds cost)"],
            "options": [
                {"id": o.id, "gate": o.gate, "valid": o.selectable,
                 "rule_ids": [v.rule_id for v in o.check.violations], "cost_usd": o.cost["total"],
                 "gate_wait_min": o.check.metrics["gate_wait_min"], "overtime_min": o.check.metrics["overtime_min"],
                 "avoidable_knock_on_min": o.check.metrics["avoidable_knock_on_min"],
                 "walk_min": o.check.metrics["walk_min"], "missed_connections": o.check.metrics["missed_connections"],
                 "ready_time": min_to_hhmm(o.check.metrics["ready_time_min"]),
                 "acdm_flags": [f["flag"] for f in o.check.metrics["acdm_flags"]]}
                for o in options
            ],
            "ranked": ranked_alternatives(options),
            "batna": None if best is None else {
                "option_id": best.id, "gate": best.gate, "cost_usd": best.cost["total"],
                "how": "reject; after round 3 the deterministic fallback decides (cheapest valid option)"},
        },
        "priorities": {
            "tier0_hard_constraints": ["C-GATE-1", "C-GATE-2", "C-TURN-1"],
            "ranked": ranked,
            "basis": "stake = max minus min dollar cost of the interest across the valid options at the "
                     "disrupted arrival; prices are team assumptions (cost_config.py)",
        },
        "notes": notes,
        "acdm": {"ready_time_update_min": ACDM_READY_UPDATE_MIN, "delay_message_min": ACDM_DELAY_MESSAGE_MIN,
                 "source": ACDM_SOURCE, "role": "soft report-only flags; never affect validity or cost"},
    }
