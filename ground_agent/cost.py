"""Ground-side cost (CLAUDE.md section 9). Pure code; weights live in cost_config.py."""
from ground_agent import cost_config as C
from ground_agent.assumptions import OVERTIME_MULTIPLIER
from ground_agent.checker import GroundCheck


# Prices the Ground-side effects of a plan from its check metrics.
# Args: check - result of check_ground for the plan.
# Returns: {"items": {name: usd}, "total": usd}, rounded to cents.
def cost_ground(check: GroundCheck) -> dict:
    m = check.metrics
    items = {
        "gate_change": C.GATE_CHANGE_FIXED if m["gate_changed"] else 0.0,
        "gate_wait": m["gate_wait_min"] * (C.GROUND_DELAY_PER_MIN + C.PAX_ONBOARD_PENALTY_PER_MIN),
        "crew_overtime": m["overtime_min"] * C.CREW_BASE_PER_MIN * OVERTIME_MULTIPLIER,
        "knock_on_delay": m["avoidable_knock_on_min"] * C.KNOCK_ON_PER_MIN,
        "missed_connections": m["missed_connections"] * C.MISSED_CONNECTION_PER_PAX,
    }
    items = {k: round(v, 2) for k, v in items.items()}
    return {"items": items, "total": round(sum(items.values()), 2)}
