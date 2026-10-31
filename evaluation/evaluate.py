"""Batch evaluation (CLAUDE.md section 13, docs/challenge-2-framing.md section 7). Pure code.

Runs the full pipeline (3 lanes -> mediator -> fallback on no consensus) on a fixed, stratified sample of
real DOT 2015 rows and compares the chosen plan with baselines on the SAME scenario, checker and cost:

  B0  status quo, ground hold   FAA-style ground delay to the first-come-first-served slot, keep the
                                scheduled gate and wait for it (no cross-domain coordination)
  B0h status quo, airborne hold depart on time, hold until the FCFS slot with ATC's extra fuel, keep the
                                scheduled gate; if the hold breaks fuel, the flight diverts (costed)
  B1  fallback least-cost       deterministic solver over menu x gates (fallback/scenario.py)
  A-x single agent decides      each agent's own round-1 favourite, no negotiation
  NEG negotiated (the system)   mediator outcome; fallback plan when there is no consensus

Ablations: checker off (would the mediator pick an unsafe plan?), extra fuel sized to the Pilot's real
holdable fuel (cross-lane fuel mismatch).

    .venv/bin/python -m evaluation.evaluate              # N = 32 + demo row, dry run (no LLM)
    .venv/bin/python -m evaluation.evaluate --live 4     # also re-run 4 scenarios with Claude round-3 votes

Outcome columns (ARRIVAL_DELAY) are read ONLY here, as a historical reference, never by an agent.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from mediator.adapters import (REPO, PROPOSERS, LaneAgent, Scenario, _atc_option, build_scenario, check_plan,
                               plan_cost, score_plans)
from mediator.core import AGENTS, Log, merge_duplicates, nash_pick, run_negotiation, shortlist

from agents.constraints import airport_limits, fuel_crew_rules
from agents.pilot import assess_plan, fuel_budget
from agents.schema import Plan
from fallback import config as fb_config
from fallback.scenario import solve_scenario
from ground_agent.checker import check_ground

from atc_agent.world_stub import event_of  # noqa: E402  (adapters put atc-agent on sys.path)

FLIGHTS = REPO / "data" / "raw" / "dot2015" / "flights.csv"
OUT = REPO / "results" / "evaluation"   # own folder: results/eval_summary.json is the live batch eval the UI shows
SAMPLE_SEED = 2015
PER_STRATUM = 8
HUBS = ("Large hub", "Medium hub")
EVENTS = ("weather", "late_aircraft")
DEMO = ("2015-04-24", "DFW", "MQ3086")
CO2_PER_KG_FUEL = 3.16
CONNECTION_USD_PER_PAX = fb_config.MISSED_CONNECTION_PER_PAX   # $200, same weight as Ground / fallback
METHODS = ("B0", "B0h", "atc_alone", "pilot_alone", "ground_alone", "NEG", "B1")
LABELS = {"B0": "Status quo: FCFS ground delay, keep gate", "B0h": "Status quo: depart on time, hold in air",
          "atc_alone": "ATC decides alone", "pilot_alone": "Pilot decides alone",
          "ground_alone": "Ground decides alone", "NEG": "Negotiated (3 agents + mediator)",
          "B1": "Fallback least-cost solver"}


# ---------------------------------------------------------------- data + sampling
def load_rows() -> dict[tuple[str, str], list[dict]]:
    by_day = defaultdict(list)
    with open(FLIGHTS, newline="") as f:
        for r in csv.DictReader(f):
            by_day[(r["MONTH"], r["DAY"])].append(r)
    return by_day


def sample(by_day) -> list[tuple[str, dict]]:
    """{Large, Medium hub} x {weather, late aircraft} x 8, fixed seed. October excluded (numeric codes)."""
    limits = airport_limits()
    strata = defaultdict(list)
    for rows in by_day.values():
        for r in rows:
            ev, lim = event_of(r), limits.get(r["DESTINATION_AIRPORT"])
            if not ev or not lim or lim.size_class not in HUBS or r["MONTH"] == "10" or not r["TAIL_NUMBER"]:
                continue
            strata[(lim.size_class, ev["type"])].append(r)
    rng = random.Random(SAMPLE_SEED)
    out = []
    for hub in HUBS:
        for ev in EVENTS:
            pool = sorted(strata[(hub, ev)], key=lambda r: (int(r["MONTH"]), int(r["DAY"]), r["AIRLINE"],
                                                            int(r["FLIGHT_NUMBER"]), r["ORIGIN_AIRPORT"]))
            out += [(f"{hub.split()[0].lower()}/{ev}", r) for r in rng.sample(pool, PER_STRATUM)]
    return out


def demo_row(by_day) -> dict:
    y, m, d = DEMO[0].split("-")
    return next(r for r in by_day[(str(int(m)), str(int(d)))]
                if r["DESTINATION_AIRPORT"] == DEMO[1] and f'{r["AIRLINE"]}{r["FLIGHT_NUMBER"]}' == DEMO[2])


# ---------------------------------------------------------------- per-plan metrics (all code)
def metrics(s: Scenario, plan: dict | None, forced_divert: bool = False) -> dict:
    """Every number for one plan on one scenario. forced_divert: the plan ran out of holding fuel, so the
    flight diverts (status quo only) and is costed as a diversion."""
    if plan is None:
        return {"valid": False, "violations": ["no plan"], "plan": None, "cost_usd": fb_config.CANCEL_COST,
                "full_cost_usd": fb_config.CANCEL_COST}
    chk = check_plan(s, plan)
    a = assess_plan("m", Plan(**plan), s.pilot_inputs, fuel_crew_rules())
    g = check_ground(Plan(**plan), s.ground_state).metrics
    opt = _atc_option(s, plan)
    cost = plan_cost(s, plan)
    focal_delay = opt.focal_delay_min if opt else a.arrival_delay_min
    knock = opt.knock_on_min if opt else 0
    pax_missed = a.pax_missed
    if forced_divert:
        all_pax = sum(c.pax for c in s.pilot_inputs.connections)
        fb = fuel_budget(s.pilot_inputs, fuel_crew_rules())
        hold = fb.holdable_before_divert_min + plan["extra_fuel_min"]   # holds until the must-divert point
        cost = (hold * fb_config.HOLDING_PER_MIN + fb_config.DIVERT_FIXED + plan["extra_fuel_min"] * 5.0
                + knock * fb_config.KNOCK_ON_BG_PER_MIN)
        pax_missed, focal_delay = all_pax, None
        fuel_kg = hold * fb.burn_kg_per_min
    else:
        fuel_kg = a.holding_fuel_kg
    return {
        "valid": chk.valid, "violations": chk.violations, "forced_divert": forced_divert,
        "plan": plan,
        "cost_usd": round(cost, 2),
        # Connection-aware: adds the Pilot's missed connections (late arrival) that plan_cost leaves out.
        "full_cost_usd": round(cost + pax_missed * CONNECTION_USD_PER_PAX, 2),
        "focal_delay_min": focal_delay, "knock_on_min": knock,
        "system_delay_min": None if focal_delay is None else focal_delay + knock,
        "ground_delay_min": plan["ground_delay_min"], "holding_min": plan["holding_min"],
        "holding_fuel_kg": round(fuel_kg), "co2_kg": round(fuel_kg * CO2_PER_KG_FUEL),
        "pax_missed": pax_missed, "fuel_margin_min": a.fuel_margin_min,
        "gate": plan["gate"], "gate_changed": g["gate_changed"], "gate_wait_min": g["gate_wait_min"],
        "crew_overtime_min": g["overtime_min"],
    }


def fcfs_option(s: Scenario, lever: str):
    """First-come-first-served slot = the earliest the queue allows (menu step 0), with the given lever."""
    first = s.atc_menu[0].arrival_slot            # menu step 0 = earliest landing the queue allows
    opts = [o for o in s.atc_menu if o.arrival_slot == first]
    if lever == "hold":
        hold = [o for o in opts if o.holding_min > 0]
        return hold[0] if hold else opts[0]
    return next(o for o in opts if o.holding_min == 0)


# ---------------------------------------------------------------- one scenario
async def evaluate_one(stratum: str, row: dict, day_rows: list[dict], live_client=None, seed: int = 7) -> dict:
    t0 = time.perf_counter()
    s = build_scenario(day_rows, row, seed=seed)
    sid = s.negotiation_id
    hist = row.get("ARRIVAL_DELAY")
    rec = {"id": sid, "stratum": stratum, "event": s.atc_world.event["type"],
           "magnitude_min": s.atc_world.event["magnitude_min"], "dest": row["DESTINATION_AIRPORT"],
           "historical_arrival_delay_min": float(hist) if hist not in ("", None) else None,
           "mode": "live" if live_client else "dry"}

    # NEG: the system as shipped (mediator + fallback when no consensus)
    log_path = OUT / "logs" / f"{sid}-{rec['mode']}.jsonl"
    log_path.unlink(missing_ok=True)
    agents = {n: LaneAgent(n, s, live=live_client is not None, client=live_client) for n in AGENTS}
    out = await run_negotiation(agents, lambda p: check_plan(s, p), lambda p: plan_cost(s, p), Log(log_path, sid),
                                {"eval": True, "stratum": stratum})
    rec["outcome"] = out.outcome
    rec["neg_why"] = None
    neg_plan = out.plan if out.outcome == "consensus" else None
    if neg_plan is None:
        fb = solve_scenario(s, "no_valid_r1" if out.outcome == "no_valid_plan" else "no_consensus_r3")
        neg_plan = fb["plan"]
        rec["neg_why"] = next((json.loads(l)["why"] for l in open(log_path) if '"step": "outcome"' in l), None)
    rec["llm_calls"] = 3 if live_client else 0
    rec["latency_s"] = round(time.perf_counter() - t0, 2)

    m = {"NEG": metrics(s, neg_plan)}
    b1 = solve_scenario(s, "baseline")
    m["B1"] = metrics(s, b1["plan"])
    rec["b1_candidates"], rec["b1_valid"] = b1["fallback"]["candidates_enumerated"], b1["fallback"]["valid"]

    gs = s.ground_state.scheduled_gate
    m["B0"] = metrics(s, fcfs_option(s, "ground").plan(gs))
    hold = fcfs_option(s, "hold").plan(gs)
    hold_fuel_ok = assess_plan("h", Plan(**hold), s.pilot_inputs, fuel_crew_rules()).fuel_ok
    m["B0h"] = metrics(s, hold, forced_divert=not hold_fuel_ok)

    proposals = {a: PROPOSERS[a](s) for a in AGENTS}
    for a in AGENTS:
        m[f"{a}_alone"] = metrics(s, proposals[a][0].plan if proposals[a] else None)

    # Ablation: checker off. Same pick rule over the unfiltered candidates (agents' own scores still apply).
    cands = merge_duplicates(proposals)
    short = shortlist(cands)
    for c in short:
        c.cost_usd = round(plan_cost(s, c.plan), 2)
        c.check = check_plan(s, c.plan)
    for a in AGENTS:
        sc = score_plans(a, s, {c.plan_id: c.plan for c in short})
        for c in short:
            c.r2_scores[a] = max(0.05, sc[c.plan_id].score)
    pick = nash_pick(short) if short else None
    rec["ablation_checker_off"] = {
        "unsafe_candidates": sum(1 for c in cands if not check_plan(s, c.plan).valid), "candidates": len(cands),
        "unsafe_agent_favourites": [a for a in AGENTS if proposals[a] and not check_plan(s, proposals[a][0].plan).valid],
        "pick_unsafe": bool(pick and not pick.check.valid),
        "pick_violations": pick.check.violations if pick else []}

    # Ablation: ATC sizes extra fuel with max(0, hold - 45); the Pilot's real holdable is 45 - alternate time.
    fb_ = fuel_budget(s.pilot_inputs, fuel_crew_rules())
    holds = [o for o in s.atc_menu if o.holding_min > 0]
    as_shipped = sum(1 for o in holds if check_plan(s, {**o.plan(gs)}).violations
                     and any(v.startswith("C-FUEL-1") for v in check_plan(s, o.plan(gs)).violations))
    fixed = 0
    for o in holds:
        p = {**o.plan(gs), "extra_fuel_min": max(0, math.ceil(o.holding_min - fb_.holdable_before_divert_min))}
        a = assess_plan("x", Plan(**p), s.pilot_inputs, fuel_crew_rules())
        fixed += 0 if a.fuel_ok else 1
    rec["ablation_extra_fuel"] = {"hold_options": len(holds), "fuel_fail_as_shipped": as_shipped,
                                  "fuel_fail_if_sized_to_pilot": fixed,
                                  "pilot_holdable_min": fb_.holdable_before_divert_min}
    neg_gate = neg_plan["gate"] if neg_plan else gs
    rec["attr"] = {"b0_cost": m["B0"]["cost_usd"],
                   "gate_only_cost": round(plan_cost(s, fcfs_option(s, "ground").plan(neg_gate)), 2)}
    rec["connecting_pax_pilot"] = sum(c.pax for c in s.pilot_inputs.connections)
    rec["m"] = m
    return rec


# ---------------------------------------------------------------- statistics
def pctl(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def boot_ci(diffs, n=4000, seed=0):
    if not diffs:
        return (None, None)
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return (round(means[int(0.025 * n)], 1), round(means[int(0.975 * n)], 1))


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def summarise(recs: list[dict]) -> dict:
    ran = [r for r in recs if "m" in r]
    # Cost comparisons only where the system produced a plan; a cancellation recommendation is a
    # different decision (to the human), reported separately rather than priced against a plan.
    ok = [r for r in ran if r["m"]["NEG"]["plan"] is not None]
    n = len(ok)
    summ = {"n_run": len(ran), "n": n, "errors": [{"id": r["id"], "error": r["error"]} for r in recs if "error" in r],
            "no_plan": [{"id": r["id"], "why": r["neg_why"]} for r in ran if r["m"]["NEG"]["plan"] is None],
            "methods": {}}
    for k in METHODS:
        ms = [r["m"][k] for r in ok]
        num = lambda f: [x[f] for x in ms if x.get(f) is not None]
        summ["methods"][k] = {
            "label": LABELS[k],
            "valid_rate": round(sum(x["valid"] for x in ms) / n, 3),
            "invalid": sum(not x["valid"] for x in ms),
            "forced_divert": sum(bool(x.get("forced_divert")) for x in ms),
            "mean_cost_usd": round(statistics.fmean(num("cost_usd"))),
            "total_cost_usd": round(sum(num("cost_usd"))),
            "mean_full_cost_usd": round(statistics.fmean(num("full_cost_usd"))),
            "total_full_cost_usd": round(sum(num("full_cost_usd"))),
            "mean_focal_delay_min": round(statistics.fmean(num("focal_delay_min")), 1),
            "p90_focal_delay_min": round(pctl(num("focal_delay_min"), 0.9), 1),
            "mean_system_delay_min": round(statistics.fmean(num("system_delay_min")), 1),
            "total_holding_min": sum(num("holding_min")),
            "total_holding_fuel_kg": sum(num("holding_fuel_kg")),
            "total_co2_kg": sum(num("co2_kg")),
            "total_pax_missed": sum(num("pax_missed")),
            "gate_changes": sum(bool(x.get("gate_changed")) for x in ms),
            "total_gate_wait_min": sum(num("gate_wait_min")),
            "total_crew_overtime_min": sum(num("crew_overtime_min")),
        }
    def paired(a, b, f):
        d = [r["m"][a][f] - r["m"][b][f] for r in ok if r["m"][a].get(f) is not None and r["m"][b].get(f) is not None]
        return {"mean_diff": round(statistics.fmean(d), 1) if d else None, "ci95": boot_ci(d), "n": len(d),
                "a_better": sum(x < 0 for x in d), "tie": sum(x == 0 for x in d), "b_better": sum(x > 0 for x in d)}
    summ["paired"] = {f"{a}_vs_{b}:{f}": paired(a, b, f)
                      for a, b in (("NEG", "B0"), ("NEG", "B0h"), ("NEG", "B1"), ("B1", "B0"))
                      for f in ("cost_usd", "full_cost_usd", "system_delay_min", "pax_missed")}
    cons = sum(r["outcome"] == "consensus" for r in ran)
    summ["negotiation"] = {
        "consensus": cons, "consensus_rate": round(cons / len(ran), 3), "consensus_ci95": wilson(cons, len(ran)),
        "outcomes": {o: sum(r["outcome"] == o for r in ran) for o in ("consensus", "no_consensus", "no_valid_plan")},
        "fallback_rate": round(1 - cons / len(ran), 3), "rounds_max": 3,
        # a leak = the system hands the human a plan that fails a hard rule
        "leaked_violations": sum(r["m"]["NEG"]["plan"] is not None and not r["m"]["NEG"]["valid"] for r in ran),
        "status_quo_invalid": sum(not r["m"]["B0"]["valid"] for r in ran),
        "neg_equals_b1": sum(r["m"]["NEG"]["plan"] == r["m"]["B1"]["plan"] for r in ok),
        "mean_latency_s": round(statistics.fmean(r["latency_s"] for r in ran), 2),
        "llm_calls_per_scenario": ran[0]["llm_calls"] if ran else 0,
        "no_consensus_reasons": dict(Counter(re.sub(r"\(\d+\)", "(n)", (r["neg_why"] or "").split(";")[0])
                                             for r in ran if r["outcome"] == "no_consensus"))}
    # Which decision produced the saving vs the status quo: the gate decision alone (status-quo slot,
    # system's gate), then the slot/lever decision on top. Code-priced with the same cost model.
    att = {"gate": [], "slot": []}
    for r in ok:
        att["gate"].append(r["attr"]["b0_cost"] - r["attr"]["gate_only_cost"])
        att["slot"].append(r["attr"]["gate_only_cost"] - r["m"]["NEG"]["cost_usd"])
    summ["attribution_vs_B0"] = {k: {"total_saving_usd": round(sum(v)), "scenarios_saving": sum(x > 0 for x in v),
                                     "scenarios_costing": sum(x < 0 for x in v)} for k, v in att.items()}
    summ["ablation_checker_off"] = {
        "scenarios_where_pick_would_be_unsafe": sum(r["ablation_checker_off"]["pick_unsafe"] for r in ran),
        "unsafe_candidates_caught": sum(r["ablation_checker_off"]["unsafe_candidates"] for r in ran),
        "candidates": sum(r["ablation_checker_off"]["candidates"] for r in ran),
        "agent_favourites_unsafe": {a: sum(a in r["ablation_checker_off"]["unsafe_agent_favourites"] for r in ran)
                                    for a in AGENTS}}
    summ["ablation_extra_fuel"] = {
        "hold_options": sum(r["ablation_extra_fuel"]["hold_options"] for r in ran),
        "fuel_fail_as_shipped": sum(r["ablation_extra_fuel"]["fuel_fail_as_shipped"] for r in ran),
        "fuel_fail_if_sized_to_pilot": sum(r["ablation_extra_fuel"]["fuel_fail_if_sized_to_pilot"] for r in ran)}
    hist = [r["historical_arrival_delay_min"] for r in ran if r["historical_arrival_delay_min"] is not None]
    summ["historical"] = {"mean_actual_arrival_delay_min": round(statistics.fmean(hist), 1) if hist else None,
                          "n": len(hist)}
    summ["by_stratum"] = {}
    for st in sorted({r["stratum"] for r in ran}):
        rs = [r for r in ok if r["stratum"] == st]
        summ["by_stratum"][st] = {
            "n": len(rs), "consensus": sum(r["outcome"] == "consensus" for r in ran if r["stratum"] == st),
            "zero_delay_all_methods": sum(r["m"]["B0"]["focal_delay_min"] == 0 and r["m"]["NEG"]["focal_delay_min"] == 0
                                          for r in rs),
            "mean_focal_delay_NEG": round(statistics.fmean(r["m"]["NEG"]["focal_delay_min"] for r in rs), 1),
            **{f"mean_full_cost_{k}": round(statistics.fmean(r["m"][k]["full_cost_usd"] for r in rs))
               for k in ("B0", "NEG", "B1")},
            "mean_hist_delay": round(statistics.fmean([r["historical_arrival_delay_min"] for r in rs
                                                       if r["historical_arrival_delay_min"] is not None] or [0]), 1)}
    return summ


# ---------------------------------------------------------------- main
async def run(live_n: int) -> None:
    by_day = load_rows()
    picks = [("demo", demo_row(by_day))] + sample(by_day)
    recs = []
    for stratum, row in picks:
        day = by_day[(row["MONTH"], row["DAY"])]
        try:
            recs.append(await evaluate_one(stratum, row, day))
        except Exception as e:                       # a failure is a result: record it, keep going
            recs.append({"id": f'{row["DESTINATION_AIRPORT"]}-{row["AIRLINE"]}{row["FLIGHT_NUMBER"]}',
                         "stratum": stratum, "error": f"{type(e).__name__}: {e}"})
        r = recs[-1]
        print(f'{r["id"]:<28} {r["stratum"]:<22} ' + (f'{r["outcome"]:<14} NEG ${r["m"]["NEG"]["full_cost_usd"]:>9,.0f} '
              f'B0 ${r["m"]["B0"]["full_cost_usd"]:>9,.0f} B1 ${r["m"]["B1"]["full_cost_usd"]:>9,.0f}'
              if "m" in r else "ERROR " + r["error"]), flush=True)
    sample_recs = [r for r in recs if r["stratum"] != "demo"]
    summary = {"generated": time.strftime("%Y-%m-%d %H:%M"), "sample_seed": SAMPLE_SEED, "world_seed": 7,
               "sample": summarise(sample_recs), "demo": next((r for r in recs if r["stratum"] == "demo"), None)}

    if live_n:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env.local")
        client = anthropic.AsyncAnthropic()
        live = []
        no_cons = {r["id"] for r in recs if r.get("outcome") == "no_consensus"}
        chosen = [picks[0]] + [(st, rw) for (st, rw), r in zip(picks, recs) if r.get("id") in no_cons][:live_n - 1]
        for stratum, row in chosen:
            try:
                live.append(await evaluate_one(stratum, row, by_day[(row["MONTH"], row["DAY"])], live_client=client))
            except Exception as e:
                live.append({"id": row["FLIGHT_NUMBER"], "stratum": stratum, "error": f"{type(e).__name__}: {e}"})
            print("live", live[-1].get("id"), live[-1].get("outcome", live[-1].get("error")), flush=True)
        summary["live"] = [{"id": r["id"], "outcome": r.get("outcome"), "error": r.get("error"),
                            "why": r.get("neg_why"), "latency_s": r.get("latency_s"),
                            "plan": r["m"]["NEG"]["plan"] if "m" in r else None,
                            "valid": r["m"]["NEG"]["valid"] if "m" in r else None} for r in live]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    with open(OUT / "rows.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r, default=str) + "\n")
    from .report import write_results
    print("Wrote", OUT / "summary.json", "and", write_results(summary, recs))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live", type=int, default=0, help="also re-run N scenarios (demo + dry-run no-consensus cases) with Claude round-3 votes")
    asyncio.run(run(p.parse_args().live))


if __name__ == "__main__":
    main()
