"""Run the fallback on one DOT row (default: DFW, 24 Apr 2015 weather) and print provenance + the chosen plan.

    python -m fallback
    python -m fallback --seed 3 --flight MQ3086
"""
import argparse
import json

from .solver import solve
from .world import build_world  # puts atc-agent/ on sys.path

from atc_agent.world_stub import load_day, pick_focal  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="2015-04-24")
    p.add_argument("--dest", default="DFW")
    p.add_argument("--flight", help="e.g. MQ3086; default = biggest weather delay in busiest weather hour")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()

    y, m, d = map(int, a.date.split("-"))
    rows = load_day(y, m, d)
    focal = pick_focal(rows, a.dest, a.flight)
    world = build_world(rows, focal, a.seed)
    print(f"Focal {world.flight} {focal['ORIGIN_AIRPORT']}->{world.dest} {world.date} | event {world.event_type} "
          f"{world.event_magnitude_min} min | background {len(world.background)} | seed {world.seed}")
    print("World provenance:")
    for field, label in world.provenance.items():
        print(f"  {field}: {label}")
    print(json.dumps(solve(world, "baseline"), indent=1))


if __name__ == "__main__":
    main()
