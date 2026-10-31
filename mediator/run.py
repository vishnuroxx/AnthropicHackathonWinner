"""Run one negotiation end to end (default: DFW, 24 Apr 2015 weather row).

    .venv/bin/python -m mediator.run              # dry run: no LLM calls
    .venv/bin/python -m mediator.run --live       # round-3 votes by the lanes' Claude agents
"""
import argparse
import asyncio
import json

from .adapters import REPO, LaneAgent, build_scenario, check_plan, plan_cost
from .core import AGENTS, Log, run_negotiation
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
    log = Log(REPO / "logs" / f"mediator-{s.negotiation_id}.jsonl", s.negotiation_id)
    out = asyncio.run(run_negotiation(agents, lambda pl: check_plan(s, pl), lambda pl: plan_cost(s, pl), log))

    print(f"Negotiation {s.negotiation_id}: {out.outcome}")
    print("Plan:", json.dumps(out.plan))
    print("Votes:", json.dumps(out.votes, indent=1))
    print("Log:", out.log_path)


if __name__ == "__main__":
    main()
