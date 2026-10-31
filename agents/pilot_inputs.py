"""Build the Pilot agent's private inputs for one focal flight (one row of flights.csv).

The world builder (role B) can call `build_pilot_inputs` or supply an equivalent PilotInputs itself.
No hindsight: outcome columns (actual times, actual delays, taxi/air times) are never read here.
"""
from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .constraints import ASSUMPTIONS, REPO, airport_limits

FLIGHTS = REPO / "data" / "raw" / "dot2015" / "flights.csv"
AIRPORTS = REPO / "data" / "raw" / "dot2015" / "airports.csv"

# Columns the Pilot may see. Outcome columns are deliberately absent (CLAUDE.md "No hindsight").
SCHEDULE_COLS = ("YEAR", "MONTH", "DAY", "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER", "ORIGIN_AIRPORT",
                 "DESTINATION_AIRPORT", "SCHEDULED_DEPARTURE", "SCHEDULED_ARRIVAL", "SCHEDULED_TIME",
                 "DISTANCE", "WEATHER_DELAY", "LATE_AIRCRAFT_DELAY")


@dataclass(frozen=True)
class Alternate:
    iata: str
    name: str
    distance_nm: float
    provenance: str = "real coordinates (airports.csv), nearest airport > 100 nm rule"


@dataclass(frozen=True)
class Connection:
    flight: str            # e.g. "DL1452"
    to: str                # onward destination
    sched_dep: str         # HH:MM, destination-local
    pax: int               # connecting passengers from the focal flight
    last_of_day: bool      # no later same-airline departure to that city in the data
    provenance: str = "real onward flight (flights.csv); pax count synthetic (seeded)"


@dataclass(frozen=True)
class PilotInputs:
    flight: str
    tail: str
    origin: str
    dest: str
    date: str                      # YYYY-MM-DD
    sched_dep: str                 # HH:MM origin-local
    sched_arr: str                 # HH:MM dest-local
    sched_time_min: int
    distance_mi: int
    aircraft_class: str            # "narrowbody" | "widebody" (assumption by distance)
    event_type: str                # "weather" | "late_aircraft"
    event_magnitude_min: int       # WEATHER_DELAY or LATE_AIRCRAFT_DELAY (reported cause minutes)
    airborne: bool                 # MVP default False (pre-departure)
    alternate: Alternate
    crew_report: str               # HH:MM origin-local (derived, approximate)
    mct_min: float
    connections: tuple[Connection, ...] = field(default_factory=tuple)
    seed: int = 0


def hhmm(s: str) -> str:
    s = s.zfill(4)
    return f"{int(s[:2]) % 24:02d}:{s[2:]}"


def to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    r_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r_nm * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_airports() -> dict[str, dict]:
    with open(AIRPORTS, newline="") as f:
        return {r["IATA_CODE"]: r for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def load_schedule() -> tuple[list[dict], dict]:
    """Schedule-only view of flights.csv plus an index by (month, day, origin)."""
    rows, by_origin_day = [], defaultdict(list)
    with open(FLIGHTS, newline="") as f:
        for r in csv.DictReader(f):
            row = {k: r[k] for k in SCHEDULE_COLS}
            rows.append(row)
            by_origin_day[(row["MONTH"], row["DAY"], row["ORIGIN_AIRPORT"])].append(row)
    return rows, by_origin_day


def nearest_alternate(dest: str, min_nm: float = 100.0) -> Alternate:
    aps = load_airports()
    d = aps[dest]
    lat, lon = float(d["LATITUDE"]), float(d["LONGITUDE"])
    best = None
    for code, a in aps.items():
        if code == dest or not a["LATITUDE"]:
            continue
        dist = haversine_nm(lat, lon, float(a["LATITUDE"]), float(a["LONGITUDE"]))
        if dist > min_nm and (best is None or dist < best[0]):
            best = (dist, code, a["AIRPORT"])
    return Alternate(iata=best[1], name=best[2], distance_nm=round(best[0], 1))


def crew_report_time(row: dict, by_origin_day) -> str:
    """Earliest scheduled departure of this tail that day (from the data) minus 60 min.
    Approximate: flights.csv contains only delayed legs, so the true first leg may be earlier."""
    tail, mo, dy = row["TAIL_NUMBER"], row["MONTH"], row["DAY"]
    first = min(to_min(hhmm(r["SCHEDULED_DEPARTURE"]))
                for (m, d, _), legs in by_origin_day.items() if m == mo and d == dy
                for r in legs if r["TAIL_NUMBER"] == tail)
    rep = max(first - int(ASSUMPTIONS["crew_report_before_first_leg_min"]), 0)
    return f"{rep // 60:02d}:{rep % 60:02d}"


def derive_connections(row: dict, by_origin_day, seed: int) -> tuple[Connection, ...]:
    """Same-airline departures from the destination 35-180 min after scheduled arrival (real flights),
    with a seeded connecting-passenger count. Undercounts: only delayed flights are in the data."""
    lo, hi = ASSUMPTIONS["connection_window_min"]
    arr = to_min(hhmm(row["SCHEDULED_ARRIVAL"]))
    rng = random.Random(f"{seed}-{row['AIRLINE']}{row['FLIGHT_NUMBER']}-{row['MONTH']}-{row['DAY']}")
    departures = by_origin_day.get((row["MONTH"], row["DAY"], row["DESTINATION_AIRPORT"]), [])
    same_airline = [r for r in departures if r["AIRLINE"] == row["AIRLINE"]]
    out = []
    for r in sorted(same_airline, key=lambda r: r["SCHEDULED_DEPARTURE"]):
        dep = to_min(hhmm(r["SCHEDULED_DEPARTURE"]))
        if lo <= dep - arr <= hi:
            later = any(x["DESTINATION_AIRPORT"] == r["DESTINATION_AIRPORT"]
                        and to_min(hhmm(x["SCHEDULED_DEPARTURE"])) > dep for x in same_airline)
            out.append(Connection(flight=f"{r['AIRLINE']}{r['FLIGHT_NUMBER']}", to=r["DESTINATION_AIRPORT"],
                                  sched_dep=hhmm(r["SCHEDULED_DEPARTURE"]),
                                  pax=rng.randint(*ASSUMPTIONS["connection_pax_range"]),
                                  last_of_day=not later))
    return tuple(out)


def build_pilot_inputs(row: dict, seed: int = 42, airborne: bool = False) -> PilotInputs:
    _, by_origin_day = load_schedule()
    row = {k: row[k] for k in SCHEDULE_COLS}  # strip outcome columns defensively
    w, l = float(row["WEATHER_DELAY"] or 0), float(row["LATE_AIRCRAFT_DELAY"] or 0)
    event = "weather" if (w > 15 and w >= l) else "late_aircraft"
    dist = int(float(row["DISTANCE"]))
    limits = airport_limits().get(row["DESTINATION_AIRPORT"])
    mct = ASSUMPTIONS["mct_min"].get(limits.size_class if limits else "", ASSUMPTIONS["mct_min"]["default"])
    return PilotInputs(
        flight=f"{row['AIRLINE']}{row['FLIGHT_NUMBER']}", tail=row["TAIL_NUMBER"],
        origin=row["ORIGIN_AIRPORT"], dest=row["DESTINATION_AIRPORT"],
        date=f"{row['YEAR']}-{int(row['MONTH']):02d}-{int(row['DAY']):02d}",
        sched_dep=hhmm(row["SCHEDULED_DEPARTURE"]), sched_arr=hhmm(row["SCHEDULED_ARRIVAL"]),
        sched_time_min=int(float(row["SCHEDULED_TIME"])), distance_mi=dist,
        aircraft_class="widebody" if dist >= ASSUMPTIONS["widebody_if_distance_mi_at_least"] else "narrowbody",
        event_type=event, event_magnitude_min=int(w if event == "weather" else l), airborne=airborne,
        alternate=nearest_alternate(row["DESTINATION_AIRPORT"]),
        crew_report=crew_report_time(row, by_origin_day), mct_min=mct,
        connections=derive_connections(row, by_origin_day, seed), seed=seed,
    )
