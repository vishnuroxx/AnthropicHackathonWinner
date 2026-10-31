"""Adapters: make the ATC, Pilot and Ground lanes speak the mediator's contract (mediator/core.py).

Nothing here edits another lane's code; it calls their public functions:
  ATC    atc-agent/atc_agent  (World, build_menu, check_slot, ATCAgent)
  Pilot  agents/              (PilotInputs, assess_plan, pilot_alternatives, PilotAgent)
  Ground ground_agent/        (WorldState, check_ground, cost_ground, free_gate_ids, GroundAgent)

Rounds 1-2 (plans + 0-1 scores) are computed from each lane's own code-side assessment, so every
number is code. Round 3 votes call the lanes' real agents (Claude) when live=True, else their dry-run
policies (ATC, Pilot) / Ground's hard check. Scores are normalised within the set being scored.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "atc-agent") not in sys.path:
    sys.path.insert(0, str(REPO / "atc-agent"))

from agents.constraints import fuel_crew_rules                       # noqa: E402
from agents.pilot import PilotAgent, _rank_key, assess_plan, pilot_alternatives  # noqa: E402
from agents.pilot_inputs import PilotInputs, build_pilot_inputs      # noqa: E402
from agents.schema import Plan                                       # noqa: E402
from atc_agent.agent import ATCAgent                                 # noqa: E402
from atc_agent.menu import Option as ATCOption, build_menu, check_slot  # noqa: E402
from atc_agent.world_stub import World, build_world as build_atc_world  # noqa: E402
from ground_agent.agent import GroundAgent                           # noqa: E402
from ground_agent.checker import check_ground                        # noqa: E402
from ground_agent.cost import cost_ground                            # noqa: E402
from ground_agent.inputs import WorldState, build_world as build_ground_world  # noqa: E402
from ground_agent.options import free_gate_ids                       # noqa: E402

from .core import PLANS_PER_AGENT, CheckResult, ScoredPlan, Vote, plan_key  # noqa: E402


@dataclass
class Scenario:
    """One disruption (one DOT row), built once per lane from the same row."""
    focal_row: dict
    atc_world: World
    atc_menu: list[ATCOption]
    pilot_inputs: PilotInputs
    ground_state: WorldState

    @property
    def negotiation_id(self) -> str:
        f = self.focal_row
        return f'{f["DESTINATION_AIRPORT"]}-{self.atc_world.date.replace("-", "")}-{f["AIRLINE"]}{f["FLIGHT_NUMBER"]}'


def build_scenario(day_rows: list[dict], focal_row: dict, seed: int = 7) -> Scenario:
    world = build_atc_world(day_rows, focal_row, seed=seed)
    ground = build_ground_world(focal_row["AIRLINE"], focal_row["FLIGHT_NUMBER"], int(focal_row["MONTH"]),
                                int(focal_row["DAY"]), focal_row["ORIGIN_AIRPORT"], seed=seed)
    return Scenario(focal_row, world, build_menu(world), build_pilot_inputs(focal_row, seed=seed), ground)


# ---------------------------------------------------------------- shared code: checker and cost
def _atc_option(s: Scenario, plan: dict) -> ATCOption | None:
    key = (plan["arrival_slot"], plan["ground_delay_min"], plan["holding_min"])
    return next((o for o in s.atc_menu if (o.arrival_slot, o.ground_delay_min, o.holding_min) == key), None)


def check_plan(s: Scenario, plan: dict) -> CheckResult:
    """Every lane's hard constraints, in code. A plan survives only if all pass."""
    violations: list[str] = []
    slot = check_slot({**plan, "gate": None}, s.atc_menu)          # C-CAP-1 (+ ATC's fuel stub)
    violations += [v for v in slot["violations"] if not v.startswith("C-FUEL-1")]  # Pilot owns fuel below
    p = Plan(**plan)
    a = assess_plan("chk", p, s.pilot_inputs, fuel_crew_rules())
    if not a.fuel_ok:
        violations.append(f"C-FUEL-1: fuel margin {a.fuel_margin_min} min < 0")
    if not a.duty_ok:
        violations.append(f"C-CREW-2: flight crew duty margin {a.duty_margin_min} min < 0")
    if plan.get("gate") is None:
        violations.append("C-GATE-1: no gate in plan")
    else:
        g = check_ground(p, s.ground_state)
        violations += [f"{v.rule_id}: {v.message}" for v in g.violations]
    return CheckResult(not violations, violations)


def plan_cost(s: Scenario, plan: dict) -> float:
    """Total system cost (USD): ATC's delay/holding/knock-on cost + Ground's gate/crew/connection cost."""
    opt = _atc_option(s, plan)
    atc_cost = opt.cost_usd if opt else 0.0
    ground_cost = cost_ground(check_ground(Plan(**plan), s.ground_state))["total"]
    return float(atc_cost) + float(ground_cost)


# ---------------------------------------------------------------- per-agent scoring (code)
# Each lane ranks plans by its own priority order (a sort key; None = breaks that lane's hard rules).
# Score = position among the distinct keys of the set being scored: best 1.0, worst 0.0, linear between.
def _key_atc(s: Scenario, p: dict):
    opt = _atc_option(s, p)
    if opt is None:
        return None, "Not in ATC arrival menu (C-CAP-1)."
    return ((opt.total_system_delay_min, opt.holding_min, opt.cost_usd),
            f"Slot {opt.arrival_slot}: system delay {opt.total_system_delay_min} min, holding {opt.holding_min} min, "
            f"cost ${opt.cost_usd}.")


def _key_pilot(s: Scenario, p: dict):
    a = assess_plan("p", Plan(**p), s.pilot_inputs, fuel_crew_rules())
    if not (a.fuel_ok and a.duty_ok):
        return None, f"Unsafe: fuel margin {a.fuel_margin_min} min, duty margin {a.duty_margin_min} min."
    return ((*_rank_key(a), a.arrival_delay_min),
            f"Fuel margin {a.fuel_margin_min} min, holding {a.holding_min} min, {a.pax_missed} pax miss "
            f"connections, arrival delay {a.arrival_delay_min} min{', divert' if a.divert else ''}.")


def _key_ground(s: Scenario, p: dict):
    if p.get("gate") is None:
        return None, "No gate."
    chk = check_ground(Plan(**p), s.ground_state)
    if not chk.valid:
        return None, "Fails " + ", ".join(v.rule_id for v in chk.violations) + "."
    c, m = cost_ground(chk), chk.metrics
    return ((c["total"], m["gate_wait_min"]),
            f"Gate {p['gate']}: wait {m['gate_wait_min']} min, overtime {m['overtime_min']} min, ground cost ${c['total']:.0f}.")


KEYS = {"atc": _key_atc, "pilot": _key_pilot, "ground": _key_ground}


def score_plans(agent: str, s: Scenario, plans: dict[str, dict]) -> dict[str, ScoredPlan]:
    keyed = {pid: KEYS[agent](s, p) for pid, p in plans.items()}
    distinct = sorted({k for k, _ in keyed.values() if k is not None})
    out = {}
    for pid, (k, why) in keyed.items():
        if k is None:
            sc = 0.0
        else:
            sc = 1.0 if len(distinct) == 1 else round(1 - distinct.index(k) / (len(distinct) - 1), 3)
        out[pid] = ScoredPlan(plans[pid], sc, why)
    return out


def feasible(agent: str, s: Scenario, plan: dict) -> bool:
    return KEYS[agent](s, plan)[0] is not None


# ---------------------------------------------------------------- round-1 plan generation (each lane's levers)
def _ground_gate(s: Scenario, plan: dict) -> str:
    """Code fills the gate for ATC/Pilot plans (contract: they leave it to Ground): Ground's cheapest valid gate
    at that arrival; the scheduled gate if none is valid (the checker then rejects the plan, visibly)."""
    best = None
    for g in [s.ground_state.scheduled_gate] + free_gate_ids(s.ground_state):
        k, _ = _key_ground(s, {**plan, "gate": g})
        if k is not None and (best is None or k < best[0]):
            best = (k, g)
    return best[1] if best else s.ground_state.scheduled_gate


def _menu_plans(s: Scenario) -> dict[str, dict]:
    """ATC's valid arrival options as full plans, gate filled by code from Ground's rules."""
    out = {}
    for o in s.atc_menu:
        if o.valid:
            p = o.plan()
            out[o.option_id] = {**p, "gate": _ground_gate(s, p)}
    return out


def _top(s: Scenario, agent: str, plans: dict[str, dict]) -> list[ScoredPlan]:
    """The agent's best 10 distinct plans that pass its own rules, best first, scored 0-1 across those 10."""
    scored = score_plans(agent, s, plans)
    seen, keep = set(), []
    for pid in sorted(scored, key=lambda k: (-scored[k].score, k)):
        p = scored[pid].plan
        if not feasible(agent, s, p) or plan_key(p) in seen:
            continue
        seen.add(plan_key(p))
        keep.append(p)
        if len(keep) == PLANS_PER_AGENT:
            break
    rescored = score_plans(agent, s, {str(i): p for i, p in enumerate(keep)})
    return [rescored[str(i)] for i in range(len(keep))]


def atc_plans(s: Scenario) -> list[ScoredPlan]:
    return _top(s, "atc", _menu_plans(s))


def pilot_plans(s: Scenario) -> list[ScoredPlan]:
    cands = {pid: Plan(**p) for pid, p in _menu_plans(s).items()}
    alts = pilot_alternatives(s.pilot_inputs, cands, fuel_crew_rules())
    return _top(s, "pilot", {a["plan_ref"]: a["plan"] for a in alts})


def ground_plans(s: Scenario) -> list[ScoredPlan]:
    gates = [s.ground_state.scheduled_gate] + free_gate_ids(s.ground_state)
    plans = {f"{pid}-{g}": {**p, "gate": g} for pid, p in _menu_plans(s).items() for g in gates}
    return _top(s, "ground", plans)


PROPOSERS = {"atc": atc_plans, "pilot": pilot_plans, "ground": ground_plans}


# ---------------------------------------------------------------- the three agents
class LaneAgent:
    """One lane behind the mediator's Agent protocol."""

    def __init__(self, name: str, s: Scenario, live: bool = False, client=None):
        self.name, self.s, self.live = name, s, live
        if name == "atc":
            self.agent = ATCAgent(s.atc_world, dry_run=not live, negotiation_id=s.negotiation_id)
        elif name == "pilot":
            self.agent = PilotAgent(client=client, dry_run=not live)
        else:
            self.agent = GroundAgent(client) if live else None

    async def propose(self) -> list[ScoredPlan]:
        return PROPOSERS[self.name](self.s)

    async def score(self, plans: dict[str, dict], others_reasons: dict[str, list[str]]) -> dict[str, ScoredPlan]:
        return score_plans(self.name, self.s, plans)

    async def vote(self, plan_id: str, plan: dict) -> Vote:
        p = Plan(**plan)
        if self.name == "atc":
            opt = _atc_option(self.s, plan)
            table = {"plan_id": plan_id, "plan": {**plan, "gate": None, "divert": False},
                     "check": check_slot({**plan, "gate": None}, self.s.atc_menu),
                     "total_system_delay_min": opt.total_system_delay_min if opt else None}
            msg = await asyncio.to_thread(self.agent.respond, 3, table, table["check"], [])
            return Vote(msg.get("action") == "accept", msg.get("reason", ""))
        if self.name == "pilot":
            msg = await self.agent.respond(self.s.pilot_inputs, plan_id, p, check_plan(self.s, plan).__dict__, [], 3)
            return Vote(msg.action == "accept", msg.reason)
        chk = check_ground(p, self.s.ground_state)
        if self.agent is None:                       # dry run: Ground accepts any plan passing its hard rules
            return Vote(chk.valid, "Passes Ground hard rules." if chk.valid else "Fails Ground hard rules.")
        msg = await self.agent.respond(self.s.ground_state, 3, plan_id, p, chk, [])
        return Vote(msg.action == "accept", msg.reason)
