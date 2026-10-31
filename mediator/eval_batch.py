"""Batch evaluation: run the full negotiation on N real DFW disruptions and compare with the fallback baseline.

    .venv/bin/python -m mediator.eval_batch              # 30 flights (15 weather + 15 late aircraft), live votes
    .venv/bin/python -m mediator.eval_batch --dry-run    # no LLM calls

Writes results/eval_flights.json (one record per flight) and results/eval_summary.json (read by the UI).
Every number comes from the mediator's own run, the same checker and the same cost function.
"""
import argparse
import asyncio
import json
import random
import time

from atc_agent.world_stub import event_of, load_day

from .adapters import REPO, LaneAgent, build_scenario, check_plan, plan_cost
from .core import AGENTS, Log, run_negotiation

RESULTS = REPO / "results"


def sample_rows(rows: list[dict], dest: str, n_each: int, seed: int) -> list[dict]:
    cands = [r for r in rows if r["DESTINATION_AIRPORT"] == dest and event_of(r)]
    rng = random.Random(seed)
    out = []
    for kind in ("weather", "late_aircraft"):
        pool = sorted((r for r in cands if event_of(r)["type"] == kind),
                      key=lambda r: (r["AIRLINE"], r["FLIGHT_NUMBER"], r["ORIGIN_AIRPORT"]))
        out += rng.sample(pool, min(n_each, len(pool)))
    return out


def run_one(rows, focal, seed, live, client) -> dict:
    from fallback.scenario import solve_scenario

    s = build_scenario(rows, focal, seed=seed)
    agents = {n: LaneAgent(n, s, live=live, client=client) for n in AGENTS}
    log = Log(REPO / "logs" / "eval" / f"{s.negotiation_id}.jsonl", s.negotiation_id)
    log.path.unlink(missing_ok=True)
    out = asyncio.run(run_negotiation(agents, lambda pl: check_plan(s, pl), lambda pl: plan_cost(s, pl), log))
    fb = solve_scenario(s, "baseline")
    rec = {"flight": s.negotiation_id, "event": s.atc_world.event["type"], "outcome": out.outcome,
           "fallback_outcome": fb["outcome"], "fallback_cost": fb["cost_usd"]}
    if out.plan:
        rec["agents_plan_cost"] = round(plan_cost(s, out.plan), 2)
        rec["chosen_plan_valid"] = check_plan(s, out.plan).valid
        rec["plan"] = out.plan
    return rec


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-each", type=int, default=15)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    client = None
    if not a.dry_run:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env.local")
        client = anthropic.AsyncAnthropic()
    rows = load_day(2015, 4, 24)
    picked = sample_rows(rows, "DFW", a.n_each, a.seed)
    recs, t0 = [], time.time()
    for i, focal in enumerate(picked, 1):
        name = f'{focal["AIRLINE"]}{focal["FLIGHT_NUMBER"]} {focal["ORIGIN_AIRPORT"]}'
        try:
            r = run_one(rows, focal, a.seed, not a.dry_run, client)
        except Exception as e:                        # record, never hide, a failed run
            r = {"flight": name, "outcome": "error", "error": repr(e)[:200]}
        recs.append(r)
        print(f"{i:2d}/{len(picked)} {name:12s} {r['outcome']}", flush=True)

    n = len(recs)
    cons = [r for r in recs if r["outcome"] == "consensus"]
    both = [r for r in cons if r.get("fallback_cost") is not None]
    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None  # noqa: E731
    summary = {
        "flights": n, "weather": sum(r.get("event") == "weather" for r in recs),
        "late_aircraft": sum(r.get("event") == "late_aircraft" for r in recs),
        "consensus": len(cons), "consensus_pct": round(100 * len(cons) / n, 1) if n else None,
        "no_consensus_or_no_valid_plan": sum(r["outcome"] in ("no_consensus", "no_valid_plan") for r in recs),
        "errors": sum(r["outcome"] == "error" for r in recs),
        "unsafe_plans_chosen": sum(1 for r in recs if r.get("plan") and not r.get("chosen_plan_valid")),
        "avg_cost_agents_usd": avg([r["agents_plan_cost"] for r in both]),
        "avg_cost_fallback_usd": avg([r["fallback_cost"] for r in both]),
        "agents_cost_le_fallback": sum(r["agents_plan_cost"] <= r["fallback_cost"] for r in both),
        "agents_cost_gt_fallback": sum(r["agents_plan_cost"] > r["fallback_cost"] for r in both),
        "mode": "dry run" if a.dry_run else "live (round-3 votes by Claude agents)",
        "seconds": round(time.time() - t0),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "eval_flights.json").write_text(json.dumps(recs, indent=1))
    (RESULTS / "eval_summary.json").write_text(json.dumps([summary], indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
