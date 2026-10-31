"""Ground cost weights (CLAUDE.md section 9). USD. Every value is an ASSUMPTION unless a source is given.

Primary metric is total system cost, so knock-on delay is priced like ground delay.
"""
# ASSUMPTION: ground delay is cheaper than airborne ($98.41/block-min, A4A 2025;
# Eurocontrol: airborne ~2x gate). Half of A4A used as the gate-side rate.
GROUND_DELAY_PER_MIN = 49.0
# ASSUMPTION: extra penalty per minute while passengers sit onboard waiting for a gate.
PAX_ONBOARD_PENALTY_PER_MIN = 20.0
# ASSUMPTION: fixed cost of a gate change (tug/ramp re-plan, signage, re-brief).
GATE_CHANGE_FIXED = 400.0
# ASSUMPTION: loaded ground crew cost, 6 crew x ~$35/h = $3.5/min; overtime is 1.5x (workbook).
CREW_BASE_PER_MIN = 3.5
# ASSUMPTION: rebooking/compensation per missed connection.
MISSED_CONNECTION_PER_PAX = 200.0
# Knock-on delay to the aircraft's next leg, same rate as ground delay.
KNOCK_ON_PER_MIN = GROUND_DELAY_PER_MIN
