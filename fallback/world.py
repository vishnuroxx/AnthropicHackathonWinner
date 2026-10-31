"""FallbackWorld: every fact the fallback rules need, built from one DOT row. Self-contained: no lane's world object.

Real: focal row (hindsight never read), same-destination background arrivals, tail's next departure.
Workbook: gates, turnaround, spare gates/fuel, crew shift, gate-change notice, runway ops.
Synthetic (seeded, labelled in `provenance`): filler arrivals, gate occupancy, crew shift end, connections.
"""
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO, REPO / "atc-agent"):  # same trick as atc-agent/atc_agent/demo.py: dirs, not packages
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agents.constraints import AirportLimits, FuelCrewRules, airport_limits, fuel_crew_rules  # noqa: E402
from agents.pilot_inputs import Alternate, nearest_alternate  # noqa: E402
from atc_agent import config as atc_config  # noqa: E402
from atc_agent.world_stub import Arrival, event_of, hhmm_to_min, weather_hours  # noqa: E402

from . import config  # noqa: E402


@dataclass(frozen=True, eq=False)  # eq=False: hashed by identity so the stream cache works
class FallbackWorld:
    # real (DOT row, hindsight never read)
    date: str
    dest: str
    flight: str
    tail: str
    airline: str
    sched_arr_min: int
    sched_time_min: int
    distance_mi: int
    event_type: str                   # "weather" | "late_aircraft"
    event_magnitude_min: int
    earliest_arr_min: int             # scheduled arrival, pushed by a late-aircraft delay
    background: tuple                 # tuple[Arrival, ...]: passive arrivals at dest (real + labelled filler)
    next_departure_min: int
    # workbook limits
    limits: AirportLimits
    fuel: FuelCrewRules
    # derived / synthetic
    normal_cap: int                   # arrivals per hour, no weather (C-CAP-1)
    hourly_cap: dict                  # hour -> arrivals per hour, cut in weather hours
    gates: tuple                      # candidate gates: scheduled + spare
    scheduled_gate: str
    gate_busy: dict                   # gate -> ((start_min, end_min), ...)
    now_min: int                      # when the disruption is announced
    crew_shift_end_min: int
    connecting_pax: int
    connection_slack_min: int
    holdable_min: int                 # holding allowed before the final reserve
    alternate: Alternate
    airborne: bool = False
    seed: int = 0
    provenance: dict = field(default_factory=dict)


# Builds the fallback world for one disrupted DOT row.
# Args: day_rows - all DOT rows of the day; focal_row - the disrupted arrival; seed - RNG seed.
# Returns: FallbackWorld (same row + seed gives the same world).
def build_world(day_rows: list[dict], focal_row: dict, seed: int = 0) -> FallbackWorld:
    dest = focal_row["DESTINATION_AIRPORT"]
    event = event_of(focal_row)
    if event is None:
        raise ValueError("focal row is not a weather / late-aircraft disruption")
    sched = hhmm_to_min(focal_row["SCHEDULED_ARRIVAL"])
    earliest = sched + (event["magnitude_min"] if event["type"] == "late_aircraft" else 0)
    limits, fuel = airport_limits()[dest], fuel_crew_rules()
    rng = random.Random(seed)
    focal_id = (focal_row["AIRLINE"], focal_row["FLIGHT_NUMBER"], focal_row["ORIGIN_AIRPORT"])

    # Background arrivals: same dest, hours covering the whole slot horizon (real), then synthetic filler.
    first_h, last_h = sched // 60 - 1, (earliest + config.HORIZON_MIN) // 60 + 1
    background: list[Arrival] = []
    real_per_hour: Counter = Counter()
    for r in day_rows:
        if r["DESTINATION_AIRPORT"] != dest or (r["AIRLINE"], r["FLIGHT_NUMBER"], r["ORIGIN_AIRPORT"]) == focal_id:
            continue
        m = hhmm_to_min(r["SCHEDULED_ARRIVAL"])
        if first_h <= m // 60 <= last_h:
            real_per_hour[m // 60] += 1
            background.append(Arrival(f'{r["AIRLINE"]}{r["FLIGHT_NUMBER"]}', r["AIRLINE"], r["TAIL_NUMBER"], m,
                                      atc_config.wake_class(r["TAIL_NUMBER"], r["AIRLINE"]), "real"))
    for h in range(first_h, last_h + 1):
        for i in range(round(real_per_hour[h] * (atc_config.FILLER_DEMAND_MULTIPLIER - 1))):
            background.append(Arrival(f"SYN{h:02d}{i:02d}", "SYN", "", h * 60 + rng.randrange(60),
                                      atc_config.DEFAULT_WAKE_CLASS, "synthetic"))
    background.sort(key=lambda a: a.sched_min)

    # Focal tail's next departure from dest later that day (real), else synthetic.
    nxt = [hhmm_to_min(r["SCHEDULED_DEPARTURE"]) for r in day_rows
           if r["TAIL_NUMBER"] == focal_row["TAIL_NUMBER"] and r["ORIGIN_AIRPORT"] == dest
           and hhmm_to_min(r["SCHEDULED_DEPARTURE"]) > sched]
    next_dep = min(nxt) if nxt else sched + config.DEFAULT_NEXT_LEG_GAP_MIN

    # Hourly arrival cap: workbook runway ops x arrival share, cut in the weather window (real, clustered).
    wx = weather_hours(day_rows, dest)
    hourly_cap = {h: atc_config.arrival_cap_per_hour(dest, h % 24 in wx) for h in range(first_h, last_h + 1)}

    # Gates: scheduled gate (next occupant arrives soon after the turnaround) + spare gates (free).
    ids = [f"{'ABCDEFGH'[i // 30]}{i % 30 + 1}" for i in range(limits.gates)]
    scheduled_gate = config.SCHEDULED_GATE
    # Small airports have one terminal (< 30 gates): fall back to other gates in terminal A.
    pool = [g for g in ids if g[0] != scheduled_gate[0]] or [g for g in ids if g != scheduled_gate]
    spares = rng.sample(pool, min(len(pool), limits.spare_gates_at_any_time))
    occupant_start = sched + limits.min_turnaround_min + rng.randint(*config.NEXT_GATE_OCCUPANT_AFTER)
    gate_busy = {scheduled_gate: ((occupant_start, occupant_start + config.NEXT_GATE_OCCUPANT_STAY),)}
    gate_busy.update({g: () for g in sorted(spares)})

    return FallbackWorld(
        date=f'{focal_row["YEAR"]}-{int(focal_row["MONTH"]):02d}-{int(focal_row["DAY"]):02d}', dest=dest,
        flight=f'{focal_row["AIRLINE"]}{focal_row["FLIGHT_NUMBER"]}', tail=focal_row["TAIL_NUMBER"],
        airline=focal_row["AIRLINE"], sched_arr_min=sched,
        sched_time_min=int(focal_row["SCHEDULED_TIME"] or 0), distance_mi=int(focal_row["DISTANCE"] or 0),
        event_type=event["type"], event_magnitude_min=event["magnitude_min"], earliest_arr_min=earliest,
        background=tuple(background), next_departure_min=next_dep, limits=limits, fuel=fuel,
        normal_cap=atc_config.arrival_cap_per_hour(dest, False), hourly_cap=hourly_cap,
        gates=(scheduled_gate, *sorted(spares)), scheduled_gate=scheduled_gate, gate_busy=gate_busy,
        now_min=earliest - 60,
        crew_shift_end_min=earliest + limits.min_turnaround_min + rng.randint(*config.CREW_END_SLACK_RANGE),
        connecting_pax=rng.randint(*config.CONNECTING_PAX_RANGE),
        connection_slack_min=rng.randint(*config.CONNECTION_SLACK_RANGE),
        holdable_min=round(fuel.spare_on_arrival_min), alternate=nearest_alternate(dest), seed=seed,
        provenance={
            "flight, tail, airline, scheduled times, distance, event type/magnitude": "real (DOT 2015)",
            "background arrivals (real part)": "real (DOT 2015, same dest, slot-horizon hours)",
            "background arrivals (filler)": f"synthetic (seed={seed}; flights.csv holds delayed flights only)",
            "next departure": "real (same tail departs dest later)" if nxt else "synthetic (no later leg in data)",
            "weather window": "real (clustered WEATHER_DELAY > 15 arrivals)",
            "hourly cap": "derived (workbook runway ops x 50% arrival share, 30% weather cut)",
            "gates, min turnaround, spare gates, crew shift length, gate-change notice": "workbook",
            "holdable fuel": "derived (workbook 45-min spare on arrival; 30-min final reserve never used)",
            "alternate airport": "real coordinates (airports.csv), nearest > 100 nm",
            "gate occupancy, crew shift end, connecting pax, slack": f"synthetic (seed={seed})",
            "wake class": "synthetic (all Large; DOT rows carry no aircraft type)",
            "flight state": "assumption: pre-departure (airborne=False)",
        },
    )
