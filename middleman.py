"""Bridge between the UI (app.py / make_cache.py) and the mediator.

`negotiate(row, seed)` runs one full negotiation and returns the dict the UI reads:
outcome ("consensus" | "halt_least_cost" | "recommend_cancel"), rounds, final_plan, log[], document, world.
Every value comes from the mediator's own JSONL log; nothing is computed here.
"""
import asyncio
import json
import os
import time

from mediator.adapters import REPO, LaneAgent, build_scenario, check_plan, plan_cost
from mediator.core import AGENTS, Log, run_negotiation
from mediator.report import render
from atc_agent.world_stub import load_day


def _find_row(spec: dict) -> tuple[list[dict], dict]:
    rows = load_day(2015, int(spec["month"]), int(spec["day"]))
    for r in rows:
        if (r["AIRLINE"], r["FLIGHT_NUMBER"], r["ORIGIN_AIRPORT"]) == (spec["airline"], spec["flight_number"], spec["origin"]):
            return rows, r
    raise LookupError(f"row not found: {spec}")


def _entry(rnd: int, agent: str, action: str, plan: dict | None, plan_id: str | None, reason: str, s, flags=()):
    chk = check_plan(s, plan) if plan else None
    return {"round": rnd, "agent": agent, "table_plan_id": plan_id,
            "message": {"action": action, "plan_id": plan_id, "plan": plan, "need": "", "offer": "",
                        "reason": reason, "flags": list(flags)},
            "checker": None if chk is None else {"valid": chk.valid, "violations": chk.violations,
                                                 "cost": plan_cost(s, plan)}}


def negotiate(row: dict, seed: int = 7, live: bool | None = None) -> dict:
    """Run one negotiation. live=None -> real Claude votes if ANTHROPIC_API_KEY is set, else a dry run."""
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env.local")
    live = bool(os.environ.get("ANTHROPIC_API_KEY")) if live is None else live
    rows, focal = _find_row(row)
    s = build_scenario(rows, focal, seed=seed)
    client = None
    if live:
        import anthropic
        client = anthropic.AsyncAnthropic()
    agents = {n: LaneAgent(n, s, live=live, client=client) for n in AGENTS}
    run_id = time.strftime("%Y%m%d-%H%M%S")
    log = Log(REPO / "logs" / f"mediator-{s.negotiation_id}-{run_id}.jsonl", s.negotiation_id)
    f = s.focal_row
    context = {"run_id": run_id, "mode": "live (round-3 votes by Claude agents)" if live else "dry run (no LLM)",
               "flight": f'{f["AIRLINE"]}{f["FLIGHT_NUMBER"]} {f["ORIGIN_AIRPORT"]}->{f["DESTINATION_AIRPORT"]}',
               "date": s.atc_world.date, "scheduled_arrival": f["SCHEDULED_ARRIVAL"], "event": s.atc_world.event,
               "seed": seed, "data": "DOT 2015 flights.csv row + organiser workbook limits",
               "synthetic_inputs": "gate occupancy, filler arrivals, connecting pax, crew report (labelled in each lane)"}
    out = asyncio.run(run_negotiation(agents, lambda pl: check_plan(s, pl), lambda pl: plan_cost(s, pl), log, context))
    fb = None
    if out.outcome != "consensus":
        from fallback.scenario import solve_scenario
        fb = solve_scenario(s, "no_valid_r1" if out.outcome == "no_valid_plan" else "no_consensus_r3")
        log.write(3, "fallback", trigger=fb["fallback"]["trigger"], outcome=fb["outcome"], plan=fb["plan"],
                  cost_usd=fb["cost_usd"], total_system_delay_min=fb["total_system_delay_min"], detail=fb["fallback"])

    # Rebuild the UI log from the mediator's own log lines.
    lines = [json.loads(x) for x in log.path.read_text().splitlines() if x.strip()]
    ui_log = []
    for l in lines:
        if l["step"] == "proposals" and l["plans"]:
            top = l["plans"][0]
            ui_log.append(_entry(1, l["agent"], "propose", top["plan"], None,
                                 f"{len(l['plans'])} plans sent; favourite: {top['reason']}", s))
        elif l["step"] == "scores":
            pick = next((x for x in lines if x["step"] == "pick"), None)
            if pick:
                sc, why = l["scores"][pick["plan_id"]]
                ui_log.append(_entry(2, l["agent"], "score", pick["plan"], pick["plan_id"],
                                     f"scored {sc} for {pick['plan_id']}: {why}", s))
        elif l["step"] == "votes":
            plan = next(x for x in lines if x["step"] == "pick")["plan"]
            for agent, v in l["votes"].items():
                ui_log.append(_entry(3, agent, "accept" if v["accept"] else "reject", plan, l["plan_id"], v["reason"], s))
    final = out.plan if out.outcome == "consensus" else (fb or {}).get("plan")
    return {"outcome": "consensus" if out.outcome == "consensus" else (fb or {}).get("outcome", out.outcome),
            "rounds": 3 if out.outcome != "no_valid_plan" else 1, "final_plan": final, "log": ui_log,
            "document": render(log.path), "world": context, "log_path": str(log.path)}
