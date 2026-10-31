"""Stand-in WorldState for the Ground agent until the shared world.py exists.

Real: the DOT 2015 row and the focal tail's next leg (when present).
Synthetic (seeded, labelled in `provenance`): gate occupancy, crew shift, connecting pax,
notice time. No outcome columns are ever read: see ALLOWED_COLUMNS.
"""
import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from limits import (
    GROUND_CREW_SHIFT_MIN,
    WALK_OTHER_TERMINAL_MIN,
    WALK_SAME_TERMINAL_MIN,
    AirportLimits,
    load_airport_limits,
)
from schema import hhmm_to_min

FLIGHTS_CSV = Path(__file__).parent / "data" / "raw" / "dot2015" / "flights.csv"
# Whitelist: outcome columns (DEPARTURE_TIME, ARRIVAL_TIME, ARRIVAL_DELAY, ...) are never read.
ALLOWED_COLUMNS = (
    "AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
    "MONTH", "DAY", "SCHEDULED_DEPARTURE", "SCHEDULED_ARRIVAL", "SCHEDULED_TIME",
    "WEATHER_DELAY", "LATE_AIRCRAFT_DELAY",
)


@dataclass(frozen=True)
class BusyWindow:
    start: int  # minutes from midnight
    end: int
    label: str


@dataclass
class WorldState:
    seed: int
    airport: str
    limits: AirportLimits
    focal_flight: str
    tail: str
    event_type: str  # "weather" | "late_aircraft"
    event_magnitude_min: int
    scheduled_arrival_min: int
    disrupted_arrival_min: int
    scheduled_gate: str
    now_min: int  # when the disruption was announced to Ground
    next_departure_min: int  # focal aircraft's next scheduled departure
    crew_shift_start_min: int
    connecting_pax: int
    connection_slack_min: int
    gate_busy: dict[str, list[BusyWindow]]
    provenance: dict[str, str] = field(default_factory=dict)

    # Ground crew shift end = start + the workbook's 8 h shift.
    # Returns: minutes from midnight.
    @property
    def crew_shift_end_min(self) -> int:
        return self.crew_shift_start_min + GROUND_CREW_SHIFT_MIN


# Terminal letter of a gate id such as "C14".
# Args: gate - gate id.
# Returns: the terminal letter.
def terminal_of(gate: str) -> str:
    return gate[0]


# Walking minutes for connecting passengers between two gates (SYNTHETIC rule).
# Args: a, b - gate ids.
# Returns: 0 if same gate, else the same/other-terminal walk time.
def walk_min(a: str, b: str) -> int:
    if a == b:
        return 0
    return WALK_SAME_TERMINAL_MIN if terminal_of(a) == terminal_of(b) else WALK_OTHER_TERMINAL_MIN


# Builds the gate id list for an airport: 30 gates per terminal A.. (SYNTHETIC layout).
# Args: n - number of gates.
# Returns: ids like "A1".."E30".
def _gate_ids(n: int) -> list[str]:
    return [f"{'ABCDEFGH'[i // 30]}{i % 30 + 1}" for i in range(n)]


# Reads the whitelisted columns of every flights.csv row.
# Args: path - CSV path.
# Returns: list of row dicts containing only ALLOWED_COLUMNS.
def _read_rows(path: Path):
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            yield {k: r[k] for k in ALLOWED_COLUMNS}


# Builds the demo WorldState for one real disrupted arrival.
# Args: airline, flight_number, month, day, origin - identify the DOT row; seed - RNG seed
#   for every synthetic field; flights_csv - data path.
# Returns: WorldState.
# Raises: LookupError if the row is not found or is not a weather/late-aircraft disruption.
def build_world(
    airline: str = "AA", flight_number: str = "1480", month: int = 4, day: int = 24,
    origin: str = "MCI", seed: int = 7, flights_csv: Path = FLIGHTS_CSV,
) -> WorldState:
    rows = [r for r in _read_rows(flights_csv) if r["MONTH"] == str(month) and r["DAY"] == str(day)]
    focal = next(
        (r for r in rows if r["AIRLINE"] == airline and r["FLIGHT_NUMBER"] == flight_number
         and r["ORIGIN_AIRPORT"] == origin),
        None,
    )
    if focal is None:
        raise LookupError("focal flight not found in flights.csv")
    weather, late = int(focal["WEATHER_DELAY"] or 0), int(focal["LATE_AIRCRAFT_DELAY"] or 0)
    if weather > 15:
        event_type, magnitude = "weather", weather
    elif late > 20:
        event_type, magnitude = "late_aircraft", late
    else:
        raise LookupError("row is not a weather/late-aircraft disruption")

    airport = focal["DESTINATION_AIRPORT"]
    limits = load_airport_limits(airport)
    sched_arr = hhmm_to_min(focal["SCHEDULED_ARRIVAL"])
    disrupted_arr = sched_arr + magnitude
    rng = random.Random(seed)

    nxt = [
        hhmm_to_min(r["SCHEDULED_DEPARTURE"]) for r in rows
        if r["TAIL_NUMBER"] == focal["TAIL_NUMBER"] and r["ORIGIN_AIRPORT"] == airport
        and hhmm_to_min(r["SCHEDULED_DEPARTURE"]) > sched_arr
    ]
    if nxt:
        next_dep, next_src = min(nxt), "real (DOT 2015, same tail departing this airport later)"
    else:
        next_dep, next_src = sched_arr + 75, "synthetic (no linked next leg in the filtered data)"

    gates = _gate_ids(limits.gates)
    scheduled_gate = "A12"
    spares = rng.sample([g for g in gates if terminal_of(g) != terminal_of(scheduled_gate)], limits.spare_gates)
    busy: dict[str, list[BusyWindow]] = {g: [] for g in gates}
    for g in gates:
        if g == scheduled_gate or g in spares:
            continue
        busy[g].append(BusyWindow(sched_arr - rng.randint(0, 60), disrupted_arr + rng.randint(30, 180), "background"))
    # The next flight planned for the focal's gate is itself held, so the gate frees late.
    busy[scheduled_gate].append(
        BusyWindow(sched_arr + 40, disrupted_arr + rng.randint(15, 28), "background (next flight at scheduled gate)")
    )

    return WorldState(
        seed=seed, airport=airport, limits=limits,
        focal_flight=f"{airline}{flight_number}", tail=focal["TAIL_NUMBER"],
        event_type=event_type, event_magnitude_min=magnitude,
        scheduled_arrival_min=sched_arr, disrupted_arrival_min=disrupted_arr,
        scheduled_gate=scheduled_gate, now_min=disrupted_arr - 60,
        next_departure_min=next_dep,
        crew_shift_start_min=disrupted_arr + rng.randint(10, 30) - GROUND_CREW_SHIFT_MIN,
        connecting_pax=rng.randint(18, 40), connection_slack_min=rng.randint(8, 20),
        gate_busy=busy,
        provenance={
            "flight, tail, scheduled times, event type/magnitude": "real (DOT 2015)",
            "next departure": next_src,
            "gate count, min turnaround, spare gates": limits.source,
            "gate occupancy, scheduled gate, crew shift, connections, announce time": f"synthetic (seed {seed})",
        },
    )
