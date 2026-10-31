"""Run the ATC agent on one DOT row (default: DFW, 24 Apr 2015 weather) for rounds 1-3.

    python -m atc_agent.demo                      # live Claude call
    python -m atc_agent.demo --dry-run            # no LLM, deterministic stand-in
    python -m atc_agent.demo --flag MINIMUM_FUEL  # Pilot raises a fuel flag in round 2
    python -m atc_agent.demo --sensitivity        # 17% weather cut instead of 30%
"""
import argparse
import json

from . import config
from .agent import ATCAgent
from .menu import Option, cheapest_valid, check_slot
from .world_stub import build_world, load_day, pick_focal


def table_plan(plan_id: str, proposed_by: str, opt: Option, menu: list[Option]) -> dict:
    return {"plan_id": plan_id, "proposed_by": proposed_by, "source_id": opt.option_id, "plan": opt.plan(),
            "check": check_slot(opt.plan(), menu), "cost_usd": opt.cost_usd,
            "total_system_delay_min": opt.total_system_delay_min}


def summary(r: dict, menu: list[Option]) -> str:
    plan = r.get("plan")
    check = check_slot(plan, menu)["status"] if plan else "n/a"
    return f'action={r["action"]} plan_id={r["plan_id"]} status={r["status"]} check={check}'


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="2015-04-24")
    p.add_argument("--dest", default="DFW")
    p.add_argument("--flight", help="e.g. MQ3086; default = biggest weather delay in busiest weather hour")
    p.add_argument("--flag", choices=["MINIMUM_FUEL", "EMERGENCY_FUEL"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sensitivity", action="store_true")
    a = p.parse_args()

    y, m, d = map(int, a.date.split("-"))
    rows = load_day(y, m, d)
    focal = pick_focal(rows, a.dest, a.flight)
    cut = config.WEATHER_CUT_SENSITIVITY if a.sensitivity else config.WEATHER_CUT
    world = build_world(rows, focal, weather_cut=cut)
    agent = ATCAgent(world, dry_run=a.dry_run)

    print(f"Negotiation {agent.negotiation_id}")
    print(f"Focal {focal['AIRLINE']}{focal['FLIGHT_NUMBER']} {focal['ORIGIN_AIRPORT']}->{a.dest} "
          f"sched arr {focal['SCHEDULED_ARRIVAL']} | event {world.event} | weather hours {world.weather_hours} "
          f"| weather cut {cut:.0%} | menu {len(agent.menu)} options")

    r1 = agent.propose()
    print("\nROUND 1", json.dumps(r1, indent=1))

    # Stand-in for the middle man: P1 = cheapest valid option (the fallback's choice).
    p1 = table_plan("P1", "fallback", cheapest_valid(agent.menu), agent.menu)
    pilot = {"from": "pilot", "round": 2, "action": "counter", "flags": [a.flag] if a.flag else [],
             "reason": "stand-in Pilot message (demo only)"}
    r2 = agent.respond(2, p1, p1["check"], [pilot])
    print(f"\nROUND 2 (table {p1['plan_id']} {p1['plan']['arrival_slot']}, Pilot flags {pilot['flags']})",
          json.dumps(r2, indent=1))

    # Round 3 table: ATC's counter becomes P2; otherwise P1 stays.
    table = p1
    if r2["action"] == "counter" and r2["status"] == "OK":
        table = table_plan("P2", "atc", next(o for o in agent.menu if o.option_id == r2["plan_id"]), agent.menu)
    r3 = agent.respond(3, table, table["check"], [pilot | {"round": 3}])
    print(f"\nROUND 3 (table {table['plan_id']} {table['plan']['arrival_slot']})", json.dumps(r3, indent=1))

    print(f"\nSUMMARY {agent.negotiation_id}")
    for n, r in enumerate((r1, r2, r3), 1):
        print(f"  R{n} {summary(r, agent.menu)} errors={len(r['validator_errors'])}")
    print(f"LLM calls logged to {agent.log_path}")


if __name__ == "__main__":
    main()
