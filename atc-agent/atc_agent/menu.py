"""Code-computed arrival options for the focal flight, plus a stub slot check.

Model: one aggregated arrival stream. Minimum headway between consecutive landings =
max(3600 / hourly arrival cap, wake gap for the pair / arrival runways). The agent never computes any of this.
"""
from dataclasses import asdict, dataclass

from . import config
from .world_stub import Arrival, World, hhmm_to_min, min_to_hhmm


@dataclass
class Option:
    option_id: str
    arrival_slot: str
    ground_delay_min: int
    holding_min: int
    extra_fuel_min: int
    focal_delay_min: int
    knock_on_min: int
    knock_on_flights: int
    total_system_delay_min: int
    cost_usd: int
    spare_slots_in_hour: int
    valid: bool
    violations: list[str]

    def plan(self, gate: str | None = None) -> dict:
        return {"arrival_slot": self.arrival_slot, "ground_delay_min": self.ground_delay_min,
                "holding_min": self.holding_min, "extra_fuel_min": self.extra_fuel_min,
                "gate": gate, "divert": False}


def _headway_s(world: World, leader: Arrival, follower: Arrival, t_min: float) -> float:
    weather = int(t_min // 60) in world.weather_hours
    cap = config.arrival_cap_per_hour(world.dest, weather, world.weather_cut)
    wake = config.wake_gap_s(leader.wake, follower.wake) / config.arrival_runways(world.dest)
    return max(3600 / cap, wake)


def sequence(world: World, arrivals: list[Arrival], ready: dict[str, float]) -> dict[str, float]:
    """First-come-first-served landing times (minutes) for arrivals ordered by ready time."""
    order = sorted(arrivals, key=lambda a: ready[a.flight_id])
    land: dict[str, float] = {}
    prev = None
    for a in order:
        t = ready[a.flight_id]
        if prev is not None:
            t = max(t, land[prev.flight_id] + _headway_s(world, prev, a, land[prev.flight_id]) / 60)
        land[a.flight_id] = t
        prev = a
    return land


def _focal_arrival(world: World) -> Arrival:
    f = world.focal
    fid = f'{f["AIRLINE"]}{f["FLIGHT_NUMBER"]}'
    return Arrival(fid, f["AIRLINE"], f["TAIL_NUMBER"], world.focal_earliest_arr_min,
                   config.wake_class(f["TAIL_NUMBER"], f["AIRLINE"]), "real")


def build_menu(world: World) -> list[Option]:
    focal = _focal_arrival(world)
    sched = hhmm_to_min(world.focal["SCHEDULED_ARRIVAL"])
    base_ready = {a.flight_id: float(a.sched_min) for a in world.background}
    base = sequence(world, world.background, base_ready)
    base_delay = {k: v - base_ready[k] for k, v in base.items()}

    seen: dict[int, Option] = {}
    options: list[Option] = []
    for step in range(0, config.SLOT_HORIZON_MIN + 1, config.SLOT_STEP_MIN):
        ready = dict(base_ready, **{focal.flight_id: float(world.focal_earliest_arr_min + step)})
        land = sequence(world, world.background + [focal], ready)
        slot = round(land[focal.flight_id])
        if slot in seen:
            continue
        knock = {k: (land[k] - base_ready[k]) - base_delay[k] for k in base}
        knock_min = round(sum(max(0.0, d) for d in knock.values()))
        knock_n = sum(1 for d in knock.values() if d > 0.5)
        hour = slot // 60
        weather = hour in world.weather_hours
        cap = config.arrival_cap_per_hour(world.dest, weather, world.weather_cut)
        spare = cap - sum(1 for t in land.values() if int(t // 60) == hour)
        wait = slot - world.focal_earliest_arr_min
        focal_delay = slot - sched
        for lever in ("ground", "hold"):
            ground, hold = (wait, 0) if lever == "ground" else (0, wait)
            if lever == "hold" and wait == 0:
                continue
            extra = max(0, hold - config.HOLDABLE_MIN)
            cost = (ground * config.GROUND_DELAY_COST_PER_MIN + hold * config.HOLDING_COST_PER_MIN
                    + extra * config.EXTRA_FUEL_COST_PER_MIN + knock_min * config.KNOCKON_COST_PER_MIN)
            opt = Option(f"O{len(options) + 1}", min_to_hhmm(slot), ground, hold, extra, focal_delay,
                         knock_min, knock_n, focal_delay + knock_min, round(cost), spare, True, [])
            options.append(opt)
        seen[slot] = options[-1]
    return options


def check_slot(plan: dict, menu: list[Option]) -> dict:
    """Stub of the checker (contract v0.2 shape): the plan must match a code-computed option exactly."""
    key = (plan.get("arrival_slot"), plan.get("ground_delay_min"), plan.get("holding_min"))
    opt = next((o for o in menu if key == (o.arrival_slot, o.ground_delay_min, o.holding_min)), None)
    violations = [] if opt is None else list(opt.violations)
    if opt is None:
        violations.append("C-CAP-1: plan not in code-computed arrival menu")
    cap_ok = opt is not None and opt.valid
    checks = [{"rule_id": "C-CAP-1", "result": "PASS" if cap_ok else "FAIL",
               "actual": opt.spare_slots_in_hour if opt else None, "limit": 0, "unit": "spare_arrival_slots_in_hour"}]
    if plan.get("holding_min") is not None:
        hold, limit = plan["holding_min"], config.HOLDABLE_MIN + (plan.get("extra_fuel_min") or 0)
        checks.append({"rule_id": "C-FUEL-1", "result": "PASS" if hold <= limit else "FAIL",
                       "actual": hold, "limit": limit, "unit": "holding_min"})
        if hold > limit:
            violations.append(f"C-FUEL-1: holding {hold} min exceeds limit {limit} min")
    valid = cap_ok and all(c["result"] == "PASS" for c in checks)
    return {"status": "VALID" if valid else "INVALID", "valid": valid, "checks": checks, "violations": violations}


def cheapest_valid(menu: list[Option]) -> Option:
    return min((o for o in menu if o.valid), key=lambda o: o.cost_usd)


def earliest_valid(menu: list[Option]) -> Option:
    return min((o for o in menu if o.valid), key=lambda o: (o.arrival_slot, o.holding_min, o.cost_usd))


def as_dicts(menu: list[Option]) -> list[dict]:
    return [{k: v for k, v in asdict(o).items() if k != "violations"} for o in menu]
