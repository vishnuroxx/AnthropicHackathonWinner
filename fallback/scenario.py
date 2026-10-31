"""Fallback on the mediator's own scenario: same ATC slot menu, same gates, same checker and cost as the
negotiation, so the fallback plan always passes the mediator's final safety check (check_plan).
fallback/world.py stays the standalone evaluation baseline.
"""
from ground_agent.options import free_gate_ids

from .solver import TIE_BREAK


# Least-cost plan that passes mediator.adapters.check_plan, or a cancellation recommendation.
# Args: s - mediator Scenario; trigger - why the fallback runs (config.TRIGGERS).
# Returns: the same dict shape as fallback.solver.solve.
def solve_scenario(s, trigger: str) -> dict:
    from mediator.adapters import check_plan, plan_cost  # lazy: mediator imports fallback

    gates = [s.ground_state.scheduled_gate] + free_gate_ids(s.ground_state)
    cands = [(o, o.plan(g)) for o in s.atc_menu for g in gates]
    scored, rejected = [], {}
    for n, (o, plan) in enumerate(cands, 1):
        chk = check_plan(s, plan)
        if not chk.valid:
            for v in chk.violations:
                rid = v.split(":")[0]
                rejected[rid] = rejected.get(rid, 0) + 1
            continue
        cost = round(plan_cost(s, plan), 2)
        key = (cost, o.total_system_delay_min, plan["holding_min"], plan["divert"], plan["arrival_slot"], plan["gate"])
        scored.append((key, f"F{n}", plan, cost, o.total_system_delay_min))
    scored.sort(key=lambda x: x[0])
    info = {"trigger": trigger, "candidates_enumerated": len(cands), "valid": len(scored), "tie_break": TIE_BREAK,
            "rejected_by_rule": dict(sorted(rejected.items())), "world": "mediator scenario (same checker as agents)"}
    if not scored:
        return {"outcome": "recommend_cancel", "proposed_by": "fallback", "plan": None,
                "check": None, "cost_usd": None, "total_system_delay_min": None,
                "fallback": info | {"selected_source_id": None, "runner_up": None,
                                    "note": "no valid plan: recommendation to the human, never auto-applied"}}
    _, sid, plan, cost, delay = scored[0]
    runner = None
    if len(scored) > 1:
        runner = {"source_id": scored[1][1], "plan": scored[1][2], "cost_usd": scored[1][3],
                  "total_system_delay_min": scored[1][4]}
    return {"outcome": "halt_least_cost", "proposed_by": "fallback", "plan": plan,
            "check": {"status": "VALID", "valid": True, "violations": []}, "cost_usd": cost,
            "total_system_delay_min": delay,
            "fallback": info | {"selected_source_id": sid, "runner_up": runner}}
