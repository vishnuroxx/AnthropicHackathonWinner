"""Hard rule checks for one plan. Pure code; rule IDs from atc-agent/agent-spec/agent-contract/rule-registry.md.

C-CAP-1 hourly arrival cap, C-WAKE-1 / C-SEP-1 spacing (seconds), C-FUEL-1 holding fuel, C-GATE-1 gate free,
C-GATE-2 gate-change notice, C-TURN-1 minimum turnaround, C-CREW-1 ground-crew overtime (hard beyond a cap).
Soft quantities (overtime, next-leg delay, missed connections, fuel margin) are returned for the cost model.
"""
import math
from collections import Counter
from functools import lru_cache

from . import config
from .world import FallbackWorld  # first: puts atc-agent/ on sys.path

from atc_agent import config as atc_config  # noqa: E402
from atc_agent.world_stub import Arrival  # noqa: E402

FOCAL = -1  # key of the focal flight in a landing stream


# Parses "HH:MM" into minutes, unwrapping past midnight relative to the world's earliest arrival.
def to_min(hhmm: str, world: FallbackWorld) -> int:
    m = int(hhmm[:2]) * 60 + int(hhmm[3:])
    return m + 1440 if m < world.earliest_arr_min - 720 else m


# Minutes to reach the alternate: cruise leg plus approach allowance (agents.constraints assumptions).
def divert_flight_min(world: FallbackWorld) -> float:
    from agents.constraints import ASSUMPTIONS
    return world.alternate.distance_nm / ASSUMPTIONS["cruise_nm_per_min"] + ASSUMPTIONS["alternate_approach_min"]


# Minimum headway in seconds between two landings: hourly cap spacing or wake gap per arrival runway.
def headway_s(world: FallbackWorld, leader: Arrival, follower: Arrival, t_min: float) -> float:
    cap = world.hourly_cap.get(int(t_min // 60), world.normal_cap)
    wake = atc_config.wake_gap_s(leader.wake, follower.wake) / atc_config.arrival_runways(world.dest)
    return max(3600 / cap, wake)


# Landing times (minutes) of the background flights, first-come-first-served at cap / wake spacing.
@lru_cache(maxsize=None)
def _base_stream(world: FallbackWorld) -> dict:
    land: dict = {}
    prev = None
    for i, arr in sorted(enumerate(world.background), key=lambda x: x[1].sched_min):
        t = float(arr.sched_min)
        if prev is not None:
            t = max(t, land[prev[0]] + headway_s(world, prev[1], arr, land[prev[0]]) / 60)
        land[i], prev = t, (i, arr)
    return land


# Landing stream with the focal flight inserted at a slot. Background flights that already land at least one
# headway before the slot keep their time; the rest are re-sequenced behind the focal flight (knock-on delay).
# Args: focal_slot - minute the focal flight lands, None for background only.
# Returns: {index in world.background (or FOCAL): landing minute}.
@lru_cache(maxsize=None)
def landing_stream(world: FallbackWorld, focal_slot: int | None = None) -> dict:
    base = _base_stream(world)
    if focal_slot is None:
        return base
    focal = focal_arrival(world)
    order = sorted(base, key=base.get)
    n = 0
    while n < len(order) and base[order[n]] + headway_s(world, world.background[order[n]], focal, base[order[n]]) / 60             <= focal_slot:
        n += 1
    land = {k: base[k] for k in order[:n]} | {FOCAL: float(focal_slot)}
    prev = (FOCAL, focal)
    for k in order[n:]:
        arr = world.background[k]
        land[k] = max(base[k], land[prev[0]] + headway_s(world, prev[1], arr, land[prev[0]]) / 60)
        prev = (k, arr)
    return land


# The focal flight as a stream arrival.
def focal_arrival(world: FallbackWorld) -> Arrival:
    return Arrival(world.flight, world.airline, world.tail, world.earliest_arr_min,
                   atc_config.wake_class(world.tail, world.airline), "real")


# Checks one plan against every hard rule.
# Args: plan - {arrival_slot "HH:MM", ground_delay_min, holding_min, extra_fuel_min, gate, divert}.
# Returns: {status, valid, checks[], violations[], flags[], soft{}}.
def check(plan: dict, world: FallbackWorld) -> dict:
    checks: list[dict] = []
    violations: list[str] = []
    divert = bool(plan.get("divert"))
    slot = to_min(plan["arrival_slot"], world)
    hold, extra = plan.get("holding_min") or 0, plan.get("extra_fuel_min") or 0

    def add(rule_id: str, ok: bool, actual, limit, unit: str, msg: str) -> None:
        checks.append({"rule_id": rule_id, "result": "PASS" if ok else "FAIL",
                       "actual": actual, "limit": limit, "unit": unit})
        if not ok:
            violations.append(f"{rule_id}: {msg}")

    # C-FUEL-1: holding <= holdable + extra fuel; a diversion must reach the alternate on the same fuel.
    need = round(divert_flight_min(world), 1) if divert else hold
    limit = world.holdable_min + extra
    add("C-FUEL-1", need <= limit, need, limit, "holding_min",
        f"{'diversion flight' if divert else 'holding'} {need} min exceeds limit {limit} min")
    margin = limit - need
    flags = ["MINIMUM_FUEL"] if margin < config.MIN_FUEL_FLAG_MIN else []

    lims = world.limits
    soft = {"fuel_margin_min": round(margin, 1), "crew_overtime_min": 0, "next_leg_delay_min": 0}
    if not divert:
        stream, base = landing_stream(world, slot), landing_stream(world, None)
        # C-CAP-1: arrivals per clock hour <= cap; the slot must also be reachable at cap spacing.
        count = Counter(int(t // 60) for t in stream.values())
        base_count = Counter(int(t // 60) for t in base.values())
        hour = slot // 60
        over = [h for h, n in count.items() if n > world.hourly_cap.get(h, world.normal_cap) and n > base_count[h]]
        cap = world.hourly_cap.get(hour, world.normal_cap)
        add("C-CAP-1", not over, count[hour], cap, "arrivals_per_hour",
            f"hour(s) {over or [hour]} over the arrival cap")
        # C-WAKE-1 / C-SEP-1: tightest gap (s) to the focal flight's leader and follower in the stream.
        order = sorted(stream, key=stream.get)
        pos = order.index(FOCAL)
        arrs = {i: a for i, a in enumerate(world.background)} | {FOCAL: focal_arrival(world)}
        pairs = []
        if pos > 0:
            ld = order[pos - 1]
            pairs.append(((slot - stream[ld]) * 60, arrs[ld], arrs[FOCAL]))
        if pos < len(order) - 1:
            fo = order[pos + 1]
            pairs.append(((stream[fo] - slot) * 60, arrs[FOCAL], arrs[fo]))
        if pairs:
            gap, lead, follow = min(pairs, key=lambda p: p[0] - atc_config.wake_gap_s(p[1].wake, p[2].wake))
            req = round(atc_config.wake_gap_s(lead.wake, follow.wake))
            known = (lead.wake, follow.wake) in atc_config.wake_table()
            add("C-WAKE-1" if known else "C-SEP-1", round(gap) >= req, round(gap), req, "s",
                f"gap {round(gap)} s below required {req} s")
        # C-GATE-1: gate free for arrival -> end of minimum turnaround.
        gate, end = plan.get("gate"), slot + lims.min_turnaround_min
        busy = world.gate_busy.get(gate)
        overlap = None if busy is None else sum(max(0, min(end, b) - max(slot, a)) for a, b in busy)
        add("C-GATE-1", overlap == 0, overlap, 0, "min", f"gate {gate} unknown or occupied for {overlap} min")
        # C-GATE-2: a gate change needs notice before arrival.
        if gate != world.scheduled_gate:
            notice = slot - world.now_min
            add("C-GATE-2", notice >= world.fuel.gate_change_notice_min, notice,
                world.fuel.gate_change_notice_min, "min", f"gate change notice {notice} min too short")
        # C-TURN-1: the gate is blocked for the full minimum turnaround above; a shortfall before the tail's
        # next departure is a soft next-leg delay, not a rule failure.
        add("C-TURN-1", True, lims.min_turnaround_min, lims.min_turnaround_min, "min", "")
        soft["next_leg_delay_min"] = max(0, end - world.next_departure_min)
        # C-CREW-1: ground-crew overtime is a soft cost, hard beyond a cap.
        ot = max(0, end - world.crew_shift_end_min)
        add("C-CREW-1", ot <= config.CREW_MAX_OVERTIME_MIN, ot, config.CREW_MAX_OVERTIME_MIN, "min",
            f"crew overtime {ot} min exceeds cap")
        soft["crew_overtime_min"] = ot
    soft["missed_pax"] = world.connecting_pax if slot - world.sched_arr_min > world.connection_slack_min else 0

    valid = all(c["result"] == "PASS" for c in checks)
    return {"status": "VALID" if valid else "INVALID", "valid": valid, "checks": checks,
            "violations": violations, "flags": flags, "soft": soft}
