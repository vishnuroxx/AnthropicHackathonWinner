"""A-CDM-style soft flags for the Ground "ready time" (TOBT-like: earliest ready for next departure).

Report-only: these flags never affect a plan's validity or cost. Thresholds are from the team's
A-CDM notes and are UNVERIFIED (ground_agent/assumptions.py). TSAT is ATC's, so out of this lane.
"""
from ground_agent.assumptions import ACDM_DELAY_MESSAGE_MIN, ACDM_READY_UPDATE_MIN, ACDM_SOURCE


# Computes the soft A-CDM flags for a plan's ready time.
# Args: ready_min - ready time (occupancy end) in minutes; reference_ready_min - the ready time last
#   reported (previous table plan) or, in round 1, the scheduled ready time; next_departure_min - the
#   next scheduled departure (EOBT stand-in).
# Returns: list of {"flag", "detail", "source"}; empty if none apply.
def acdm_flags(ready_min: int, reference_ready_min: int, next_departure_min: int) -> list[dict]:
    flags = []
    shift = ready_min - reference_ready_min
    if abs(shift) > ACDM_READY_UPDATE_MIN:
        flags.append({
            "flag": "READY_TIME_UPDATE",
            "detail": f"ready time moved {shift:+d} min (more than {ACDM_READY_UPDATE_MIN}): re-report it",
            "source": ACDM_SOURCE,
        })
    late = ready_min - next_departure_min
    if late > ACDM_DELAY_MESSAGE_MIN:
        flags.append({
            "flag": "DELAY_MESSAGE",
            "detail": f"ready {late} min after the next scheduled departure (more than {ACDM_DELAY_MESSAGE_MIN}): delay message needed",
            "source": ACDM_SOURCE,
        })
    return flags
