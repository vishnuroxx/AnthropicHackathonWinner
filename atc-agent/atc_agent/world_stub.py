"""Stub world for the ATC agent until team B's build_world lands.

Real: focal row, background arrivals (same dest + date), weather window (clustered weather-delayed arrivals).
Synthetic: filler arrivals (flights.csv holds delayed flights only), wake class default.
"""
import csv
import random
from collections import Counter
from dataclasses import dataclass, field

from . import config


@dataclass
class Arrival:
    flight_id: str
    airline: str
    tail: str
    sched_min: int           # scheduled arrival, minutes after local midnight
    wake: str
    provenance: str          # "real" or "synthetic"


@dataclass
class World:
    date: str
    dest: str
    focal: dict                       # focal row with hindsight columns removed
    event: dict                       # {"type": "weather"|"late_aircraft", "magnitude_min": int}
    focal_earliest_arr_min: int       # scheduled arrival, pushed by late-aircraft delay
    weather_hours: list[int]
    background: list[Arrival]
    weather_cut: float = config.WEATHER_CUT
    notes: list[str] = field(default_factory=list)


def hhmm_to_min(v: str) -> int:
    v = int(v)
    return (v // 100) * 60 + v % 100


def min_to_hhmm(m: int) -> str:
    m %= 24 * 60
    return f"{m // 60:02d}:{m % 60:02d}"


def load_day(year: int, month: int, day: int) -> list[dict]:
    with open(config.FLIGHTS_CSV, newline="") as f:
        return [r for r in csv.DictReader(f)
                if r["YEAR"] == str(year) and r["MONTH"] == str(month) and r["DAY"] == str(day)]


def _num(v: str) -> float:
    return float(v) if v not in ("", None) else 0.0


def event_of(row: dict) -> dict | None:
    if _num(row["WEATHER_DELAY"]) > 15:
        return {"type": "weather", "magnitude_min": int(_num(row["WEATHER_DELAY"]))}
    if _num(row["LATE_AIRCRAFT_DELAY"]) > 20:
        return {"type": "late_aircraft", "magnitude_min": int(_num(row["LATE_AIRCRAFT_DELAY"]))}
    return None


def strip_hindsight(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in config.HINDSIGHT_COLUMNS}


def weather_hours(day_rows: list[dict], dest: str) -> list[int]:
    counts = Counter(hhmm_to_min(r["SCHEDULED_ARRIVAL"]) // 60 for r in day_rows
                     if r["DESTINATION_AIRPORT"] == dest and _num(r["WEATHER_DELAY"]) > 15)
    return sorted(h for h, n in counts.items() if n >= config.WEATHER_WINDOW_MIN_DELAYED)


def pick_focal(day_rows: list[dict], dest: str, flight: str | None = None) -> dict:
    """Default focal: the weather-delayed arrival with the largest WEATHER_DELAY in the busiest weather hour."""
    arrivals = [r for r in day_rows if r["DESTINATION_AIRPORT"] == dest and event_of(r)]
    if flight:
        return next(r for r in arrivals if f'{r["AIRLINE"]}{r["FLIGHT_NUMBER"]}' == flight)
    wx = weather_hours(day_rows, dest)
    busiest = max(wx, key=lambda h: sum(1 for r in arrivals if hhmm_to_min(r["SCHEDULED_ARRIVAL"]) // 60 == h))
    in_hour = [r for r in arrivals if hhmm_to_min(r["SCHEDULED_ARRIVAL"]) // 60 == busiest and _num(r["WEATHER_DELAY"]) > 15]
    return max(in_hour, key=lambda r: _num(r["WEATHER_DELAY"]))


def build_world(day_rows: list[dict], focal_row: dict, seed: int = 0,
                weather_cut: float = config.WEATHER_CUT) -> World:
    dest = focal_row["DESTINATION_AIRPORT"]
    event = event_of(focal_row)
    sched = hhmm_to_min(focal_row["SCHEDULED_ARRIVAL"])
    earliest = sched + (event["magnitude_min"] if event["type"] == "late_aircraft" else 0)
    hours = range(sched // 60 - config.HORIZON_HOURS, sched // 60 + config.HORIZON_HOURS + 2)

    background: list[Arrival] = []
    real_per_hour: Counter = Counter()
    for r in day_rows:
        if r is focal_row or r["DESTINATION_AIRPORT"] != dest:
            continue
        m = hhmm_to_min(r["SCHEDULED_ARRIVAL"])
        if m // 60 in hours:
            real_per_hour[m // 60] += 1
            background.append(Arrival(f'{r["AIRLINE"]}{r["FLIGHT_NUMBER"]}', r["AIRLINE"], r["TAIL_NUMBER"], m,
                                      config.wake_class(r["TAIL_NUMBER"], r["AIRLINE"]), "real"))

    rng = random.Random(f"{seed}-{focal_row['AIRLINE']}{focal_row['FLIGHT_NUMBER']}")
    for h in hours:
        n_fill = round(real_per_hour[h] * (config.FILLER_DEMAND_MULTIPLIER - 1))
        for i in range(n_fill):
            background.append(Arrival(f"SYN{h:02d}{i:02d}", "SYN", "", h * 60 + rng.randrange(60),
                                      config.DEFAULT_WAKE_CLASS, "synthetic"))
    background.sort(key=lambda a: a.sched_min)

    return World(
        date=f'{focal_row["YEAR"]}-{int(focal_row["MONTH"]):02d}-{int(focal_row["DAY"]):02d}',
        dest=dest, focal=strip_hindsight(focal_row), event=event, focal_earliest_arr_min=earliest,
        weather_hours=weather_hours(day_rows, dest), background=background, weather_cut=weather_cut,
        notes=[f"filler multiplier {config.FILLER_DEMAND_MULTIPLIER:.2f}x real arrivals per hour (synthetic)"],
    )
