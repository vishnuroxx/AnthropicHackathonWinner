"""Run one negotiation end to end (default: DFW, 24 Apr 2015 weather row).

    .venv/bin/python -m mediator.run              # dry run: no LLM calls
    .venv/bin/python -m mediator.run --live       # round-3 votes by the lanes' Claude agents
"""
import argparse
import asyncio
import json
import time

from .adapters import REPO, LaneAgent, build_scenario, check_plan, plan_cost
from .core import AGENTS, Log, run_negotiation
from .report import write_report
from atc_agent.world_stub import load_day, pick_focal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="2015-04-24")
    p.add_argument("--dest", default="DFW")
    p.add_argument("--flight", help="e.g. MQ3086; default = biggest weather delay in the busiest weather hour")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()

    y, m, d = map(int, a.date.split("-"))
    rows = load_day(y, m, d)
    s = build_scenario(rows, pick_focal(rows, a.dest, a.flight), seed=a.seed)
    client = None
    if a.live:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env.local")
        client = anthropic.AsyncAnthropic()
    agents = {n: LaneAgent(n, s, live=a.live, client=client) for n in AGENTS}
    run_id = time.strftime("%Y%m%d-%H%M%S")
    log = Log(REPO / "logs" / f"mediator-{s.negotiation_id}-{run_id}.jsonl", s.negotiation_id)   # one file per run
    f = s.focal_row
    context = {"run_id": run_id, "mode": "live (round-3 votes by Claude agents)" if a.live else "dry run (no LLM)",
               "flight": f'{f["AIRLINE"]}{f["FLIGHT_NUMBER"]} {f["ORIGIN_AIRPORT"]}->{f["DESTINATION_AIRPORT"]}',
               "date": s.atc_world.date, "scheduled_arrival": f["SCHEDULED_ARRIVAL"],
               "event": s.atc_world.event, "seed": a.seed, "data": "DOT 2015 flights.csv row + organiser workbook limits",
               "synthetic_inputs": "gate occupancy, filler arrivals, connecting pax, crew report (labelled in each lane)"}
    out = asyncio.run(run_negotiation(agents, lambda pl: check_plan(s, pl), lambda pl: plan_cost(s, pl), log, context))
    fb = None
    if out.outcome != "consensus":                    # deterministic non-AI fallback (fallback/ lane)
        from fallback.solver import solve
        from fallback.world import build_world as build_fallback_world
        trigger = "no_valid_r1" if out.outcome == "no_valid_plan" else "no_consensus_r3"
        fb = solve(build_fallback_world(rows, s.focal_row, a.seed), trigger)
        log.write(3, "fallback", trigger=trigger, outcome=fb["outcome"], plan=fb["plan"], cost_usd=fb["cost_usd"],
                  total_system_delay_min=fb["total_system_delay_min"], detail=fb["fallback"])
    report = write_report(log.path)

    print(f"Negotiation {s.negotiation_id}: {out.outcome}")
    print("Plan:", json.dumps(out.plan))
    print("Votes:", json.dumps(out.votes, indent=1))
    if fb:
        print(f"Fallback ({fb['fallback']['trigger']}): {fb['outcome']}", json.dumps(fb["plan"]))
    print("Log:", out.log_path)
    print("Decision record:", report)


if __name__ == "__main__":
    main()
