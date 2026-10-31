"""ATC facts block (injected into the prompt). ATC facts only: no Pilot/Ground facts, no outcome columns."""
import json
from collections import Counter

from . import config
from .menu import Option, as_dicts
from .world_stub import World, min_to_hhmm

FOCAL_FIELDS = ("YEAR", "MONTH", "DAY", "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER", "ORIGIN_AIRPORT",
                "DESTINATION_AIRPORT", "SCHEDULED_DEPARTURE", "SCHEDULED_ARRIVAL", "SCHEDULED_TIME", "DISTANCE")


def build_atc_facts(world: World, menu: list[Option], flags: set[str]) -> dict:
    per_hour = Counter((a.sched_min // 60, a.provenance) for a in world.background)
    hours = sorted({h for h, _ in per_hour})
    cap = config.airport_capacity(world.dest)
    facts = {
        "event": world.event | {"provenance": "real"},
        "focal_flight": {k: world.focal[k] for k in FOCAL_FIELDS} | {
            "earliest_arrival": min_to_hhmm(world.focal_earliest_arr_min), "provenance": "real"},
        "airport": {"iata": world.dest, "active_runways": cap["active_runways"],
                    "max_runway_ops_per_hour": cap["max_runway_ops_per_hour"], "provenance": "organiser workbook"},
        "weather_window_hours": world.weather_hours,
        "arrival_demand_vs_cap": [
            {"hour": f"{h:02d}:00", "real_arrivals": per_hour[(h, "real")],
             "synthetic_filler": per_hour[(h, "synthetic")],
             "arrival_cap": config.arrival_cap_per_hour(world.dest, h in world.weather_hours, world.weather_cut),
             "weather": h in world.weather_hours} for h in hours],
        "wake": {"default_class": config.DEFAULT_WAKE_CLASS,
                 "gap_large_large_s": round(config.wake_gap_s("Large", "Large")),
                 "provenance": "organiser table; class synthetic"},
        "fuel_flags_from_pilot": sorted(flags),
        "option_menu": as_dicts(menu),
        "labels": {"capacity": "derived: 50% arrivals; weather cut synthetic",
                   "filler": "synthetic arrivals; flights.csv holds delayed flights only",
                   "cost": "stub until team cost model"},
    }
    text = json.dumps(facts)
    leaked = {c for c in config.HINDSIGHT_COLUMNS if f'"{c}"' in text}
    assert not leaked, f"hindsight columns in ATC facts: {leaked}"
    return facts
