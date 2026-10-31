"""Ground-side assumptions the organiser workbook does not give.

Mirrors the Pilot lane's ASSUMPTIONS dict (agents/constraints.py). Organiser rule: any limit we
add or change must be stated in the demo, so `ASSUMPTIONS` is printed by ground_agent.demo.
Limits that ARE in the workbook (crew shift, gate-change notice, gates, minimum turnaround) are
read at runtime from agents.constraints and are not repeated here.
"""
# Not in the workbook: longest a landed aircraft may wait for its gate before C-GATE-1 fails.
MAX_GATE_WAIT_MIN = 30
# Workbook fuel_and_crew text: "8 hours; overtime costs 1.5x after that". agents.constraints parses
# only the first number (the 8), so the multiplier is kept here with that citation.
OVERTIME_MULTIPLIER = 1.5
# Not in the workbook: walking minutes for connecting passengers after a gate change.
WALK_SAME_TERMINAL_MIN = 5
WALK_OTHER_TERMINAL_MIN = 15
# A-CDM soft flags (ground_agent/acdm.py). Thresholds come from the team's A-CDM notes (Dublin ground
# handler guide); the source PDFs have NOT been read, so they are labelled unverified everywhere.
ACDM_READY_UPDATE_MIN = 5
ACDM_DELAY_MESSAGE_MIN = 15
ACDM_SOURCE = "team notes; Dublin A-CDM guide not yet read, unverified"
# Interests whose rank is worse than this (of 7) are called out against the brief's stated Ground objectives.
LOW_RANK_FROM = 4
# Provenance label for the airport limits (the sheet itself says these are synthetic).
LIMITS_SOURCE = "organiser workbook, airport_capacity (SYNTHETIC planning limits)"

ASSUMPTIONS = {
    "max_gate_wait_min": {"value": MAX_GATE_WAIT_MIN, "source": "team assumption, not in workbook"},
    "overtime_multiplier": {"value": OVERTIME_MULTIPLIER, "source": "workbook fuel_and_crew text (1.5x after 8 h)"},
    "walk_same_terminal_min": {"value": WALK_SAME_TERMINAL_MIN, "source": "team assumption (synthetic)"},
    "walk_other_terminal_min": {"value": WALK_OTHER_TERMINAL_MIN, "source": "team assumption (synthetic)"},
    "acdm_ready_update_min": {"value": ACDM_READY_UPDATE_MIN, "source": ACDM_SOURCE},
    "acdm_delay_message_min": {"value": ACDM_DELAY_MESSAGE_MIN, "source": ACDM_SOURCE},
    "gate_layout": {"value": "30 gates per terminal, seeded occupancy", "source": "synthetic (seeded)"},
    "cost_weights": {"value": "see ground_agent/cost_config.py", "source": "team assumptions (labelled there)"},
}
