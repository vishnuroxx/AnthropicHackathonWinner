"""Fallback solver parameters. Every value is labelled: workbook, real, derived or synthetic.

Workbook limits (gates, turnaround, spare fuel, crew shift, gate-change notice, wake table, runway ops)
are read at run time from the organiser workbook via agents.constraints / atc_agent.config, never hardcoded.
"""

# --- Enumeration (synthetic) ---
SLOT_MIN = 5                      # arrival slot grid, minutes
HORIZON_MIN = 180                 # latest slot considered: earliest arrival + 3 h
EXTRA_FUEL_OPTIONS = (0, 15, 30)  # extra holding fuel loaded for a hold plan, minutes
TRIGGERS = ("no_consensus_r3", "no_valid_r1", "agent_error", "malformed_twice", "refusal", "max_tokens",
            "baseline")

# --- Safety flag (CLAUDE.md pilot red line) ---
MIN_FUEL_FLAG_MIN = 10            # fuel margin below this -> MINIMUM_FUEL flag (soft)

# --- Synthetic world ---
SCHEDULED_GATE = "A12"            # same synthetic choice as ground_agent.inputs
CONNECTING_PAX_RANGE = (18, 40)   # seeded uniform
CONNECTION_SLACK_RANGE = (8, 20)  # minutes, seeded uniform
CREW_END_SLACK_RANGE = (10, 40)   # shift ends this long after the minimum-turnaround finish, seeded
NEXT_GATE_OCCUPANT_AFTER = (0, 20)  # next flight due at the scheduled gate, after turnaround, seeded
NEXT_GATE_OCCUPANT_STAY = 60      # minutes the next occupant holds the scheduled gate
DEFAULT_NEXT_LEG_GAP_MIN = 75     # when the tail has no later departure in the data
CREW_MAX_OVERTIME_MIN = 120       # synthetic hard cap on ground-crew overtime (C-CREW-1)

# --- Cost weights, USD ---
HOLDING_PER_MIN = 98.0            # ~$98/block-min (Airlines for America 2025, CLAUDE.md section 9)
GROUND_DELAY_PER_MIN = 49.0       # holding ~2x gate delay (Eurocontrol); ground_agent/cost_config.py
EXTRA_FUEL_PER_MIN = 5.0          # synthetic; atc_agent/config.py
KNOCK_ON_BG_PER_MIN = 98.0        # background arrivals absorb delay airborne; atc_agent/config.py
NEXT_LEG_PER_MIN = 49.0           # delay to the tail's next departure; ground_agent/cost_config.py
GATE_CHANGE_FIXED = 400.0         # synthetic; ground_agent/cost_config.py
CREW_BASE_PER_MIN = 3.5           # synthetic; ground_agent/cost_config.py
CREW_OVERTIME_MULT = 1.5          # workbook: overtime at 1.5x
MISSED_CONNECTION_PER_PAX = 200.0  # synthetic; ground_agent/cost_config.py
DIVERT_FIXED = 25000.0            # synthetic, large fixed cost
CANCEL_COST = 100000.0            # synthetic, largest; recommendation to the human only

# --- Outcome columns the world may never read (CLAUDE.md "No hindsight") ---
HINDSIGHT_COLUMNS = frozenset({
    "DEPARTURE_TIME", "ARRIVAL_TIME", "ARRIVAL_DELAY", "DEPARTURE_DELAY", "WHEELS_ON", "WHEELS_OFF",
    "ELAPSED_TIME", "AIR_TIME", "TAXI_IN", "TAXI_OUT",
})
