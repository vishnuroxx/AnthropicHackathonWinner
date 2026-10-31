"""ATC agent parameters. Every value is labelled: organiser, real, derived or synthetic.

Organiser limits are read from the Challenge #2 workbook and override CLAUDE.md.
Spec: _bmad-output/specs/spec-atc-agent/ (private-state.md, research.md).
"""
from functools import lru_cache
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[2]
WORKBOOK = REPO / "data/raw/challenge2/challenge-2-operational-constraints.xlsx"
FLIGHTS_CSV = REPO / "data/raw/dot2015/flights.csv"

# --- Wake class (synthetic, adjustable) ---
# DOT rows carry no aircraft type. FAA: CRJ/ERJ/737/A320 all weigh 41,000-300,000 lb = Large (research A10).
DEFAULT_WAKE_CLASS = "Large"
# Fill from real aircraft data when available: tail number or airline code -> Super/Heavy/Large/Small.
WAKE_OVERRIDES: dict[str, str] = {}

# --- Spacing (derived) ---
APPROACH_SPEED_KT = 140  # fleet midpoint: 737-700 130 kt, 737-800 142 kt (research A11)

# --- Capacity (derived from organiser runway ops/h) ---
ARRIVAL_SHARE = 0.5          # balanced arrival/departure rates, as in FAA capacity profiles
WEATHER_CUT = 0.30           # convective cut: ATL 100->70, SFO 54->36 (research A5, A14)
WEATHER_CUT_SENSITIVITY = 0.17  # DFW IMC cut, FAA profile 2018 ~204->170 ops/h (research A12)
WEATHER_WINDOW_MIN_DELAYED = 5  # hour is in the weather window if >= this many WEATHER_DELAY>15 arrivals (real data)

# --- Synthetic filler arrivals ---
# flights.csv holds delayed flights only. DFW 24 Apr 2015: 203 arrivals vs ~933 real (681,261 movements in 2015).
FILE_SHARE_OF_REAL = 203 / 933           # 0.218, DFW-derived (research A13)
CAPACITY_SCALE = 90 / 200                # workbook DFW ops/h vs real ~200 (research A12)
FILLER_DEMAND_MULTIPLIER = CAPACITY_SCALE / FILE_SHARE_OF_REAL  # ~2.06x file arrivals per hour

# --- Option menu (synthetic) ---
SLOT_STEP_MIN = 5
SLOT_HORIZON_MIN = 90
HORIZON_HOURS = 1  # focal hour +/- 1 h

# --- Fuel (organiser) --- spare fuel on arrival = 45 min of holding unless stated otherwise.
HOLDABLE_MIN = 45

# --- Cost stub (until team B's cost model lands) ---
HOLDING_COST_PER_MIN = 98.0       # ~$98/block-min (Airlines for America 2025, CLAUDE.md §9)
GROUND_DELAY_COST_PER_MIN = 49.0  # holding ~2x gate delay (Eurocontrol, research A8)
EXTRA_FUEL_COST_PER_MIN = 5.0     # synthetic
KNOCKON_COST_PER_MIN = HOLDING_COST_PER_MIN  # background flights near arrival absorb delay airborne (assumption)

# --- Agent contract v0.2 (hybrid) ---
SCHEMA_VERSION = "0.2-hybrid"
RULESET_ID = "challenge2-workbook-2026-10-31"
FLAGS = ("MINIMUM_FUEL", "EMERGENCY_FUEL")  # closed enum, agent contract v0.2
CAP10_TOLERANCE_MIN = 5  # counter only if own option beats the table by >= this much total system delay

# --- Model ---
MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 700
HINDSIGHT_COLUMNS = frozenset({
    "DEPARTURE_TIME", "ARRIVAL_TIME", "ARRIVAL_DELAY", "DEPARTURE_DELAY", "WHEELS_ON", "WHEELS_OFF",
    "ELAPSED_TIME", "AIR_TIME", "TAXI_IN", "TAXI_OUT",
    # delay-cause columns are outcomes too, except the event magnitude itself
    "AIR_SYSTEM_DELAY", "SECURITY_DELAY", "AIRLINE_DELAY", "DIVERTED", "CANCELLED", "CANCELLATION_REASON",
})

WAKE_CLASSES = ("Super", "Heavy", "Large", "Small")


@lru_cache(maxsize=1)
def wake_table() -> dict[tuple[str, str], float]:
    """(leader, follower) -> minimum separation in NM, from the workbook. Missing pairs use the 'any other' value."""
    ws = openpyxl.load_workbook(WORKBOOK, data_only=True)["wake_separation"]
    table: dict[tuple[str, str], float] = {}
    for leader, follower, nm, *_ in ws.iter_rows(values_only=True):
        if leader is None or not isinstance(nm, (int, float)):
            continue  # note and header rows
        if str(leader).startswith("Any other"):
            table[("*", "*")] = float(nm)
        else:
            table[(str(leader).split(" ")[0], str(follower))] = float(nm)
    return table


def wake_gap_s(leader: str, follower: str) -> float:
    table = wake_table()
    nm = table.get((leader, follower), table[("*", "*")])
    return nm / APPROACH_SPEED_KT * 3600


@lru_cache(maxsize=None)
def airport_capacity(iata: str) -> dict:
    ws = openpyxl.load_workbook(WORKBOOK, data_only=True)["airport_capacity"]
    rows = ws.iter_rows(values_only=True)
    header = next(r for r in rows if r[0] == "IATA_CODE")
    for row in rows:
        if row[0] == iata:
            return dict(zip(header, row))
    raise KeyError(f"{iata} not in workbook airport_capacity")


def arrival_cap_per_hour(iata: str, weather: bool, cut: float = WEATHER_CUT) -> int:
    cap = airport_capacity(iata)["max_runway_ops_per_hour"] * ARRIVAL_SHARE
    return round(cap * (1 - cut)) if weather else round(cap)


def arrival_runways(iata: str) -> int:
    return max(1, airport_capacity(iata)["active_runways"] // 2)


def wake_class(tail: str, airline: str) -> str:
    return WAKE_OVERRIDES.get(tail) or WAKE_OVERRIDES.get(airline) or DEFAULT_WAKE_CLASS
