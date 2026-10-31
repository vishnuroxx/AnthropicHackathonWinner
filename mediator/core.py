"""Mediator: pure code, no LLM. Runs the three-round negotiation and decides every step.

Round 1: each agent returns up to 10 full plans, scored 0-1 (1 = most favourable), each with a reason.
Mediator: merge duplicates -> drop plans that fail any hard constraint -> shortlist each agent's top 3.
Round 2: each agent scores the whole shortlist (seeing the other agents' round-1 reasons).
Mediator: pick the plan with the highest Pilot x Ground x ATC x cost_score.
Round 3: each agent accepts or rejects that plan. All accept -> consensus; otherwise no consensus
(the human-in-the-loop fallback is a separate lane; this module only reports it).

Agents are anything that implements the `Agent` protocol below (see mediator/adapters.py).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Protocol

AGENTS = ("atc", "pilot", "ground")
PLANS_PER_AGENT = 10
SHORTLIST_PER_AGENT = 3
SCORE_FLOOR = 0.05          # a 0 would zero the product and act as a veto; vetoes belong to the checker
PLAN_FIELDS = ("arrival_slot", "ground_delay_min", "holding_min", "extra_fuel_min", "gate", "divert")


@dataclass(frozen=True)
class ScoredPlan:
    """One plan as an agent sends it: the full plan, the agent's 0-1 score, and why."""
    plan: dict
    score: float
    reason: str


@dataclass(frozen=True)
class Vote:
    accept: bool
    reason: str


@dataclass(frozen=True)
class CheckResult:
    valid: bool
    violations: list[str]             # each starts with a rule id, e.g. "C-FUEL-1: ..."


class Agent(Protocol):
    name: str

    async def propose(self) -> list[ScoredPlan]: ...
    async def score(self, plans: dict[str, dict], others_reasons: dict[str, list[str]]) -> dict[str, ScoredPlan]: ...
    async def vote(self, plan_id: str, plan: dict) -> Vote: ...


@dataclass
class Candidate:
    plan_id: str
    plan: dict
    proposed_by: list[str]
    r1_scores: dict[str, float] = field(default_factory=dict)
    r1_reasons: dict[str, str] = field(default_factory=dict)
    check: CheckResult | None = None
    cost_usd: float | None = None
    r2_scores: dict[str, float] = field(default_factory=dict)
    r2_reasons: dict[str, str] = field(default_factory=dict)
    product: float | None = None


@dataclass
class Outcome:
    outcome: str                      # "consensus" | "no_consensus" | "no_valid_plan"
    plan_id: str | None
    plan: dict | None
    votes: dict[str, dict]
    candidates: list[dict]
    log_path: str


def plan_key(plan: dict) -> tuple:
    """Two plans are duplicates when every plan field is equal."""
    return tuple(plan.get(f) for f in PLAN_FIELDS)


def clamp_score(x) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return SCORE_FLOOR
    return min(1.0, max(SCORE_FLOOR, x))


def merge_duplicates(proposals: dict[str, list[ScoredPlan]]) -> list[Candidate]:
    """Round 1 output -> unique candidates, keeping every proposer's score and reason."""
    by_key: dict[tuple, Candidate] = {}
    for agent in AGENTS:
        for sp in proposals.get(agent, [])[:PLANS_PER_AGENT]:
            key = plan_key(sp.plan)
            c = by_key.get(key)
            if c is None:
                c = by_key[key] = Candidate(f"C{len(by_key) + 1}", dict(sp.plan), [])
            if agent not in c.proposed_by:
                c.proposed_by.append(agent)
                c.r1_scores[agent] = clamp_score(sp.score)
                c.r1_reasons[agent] = sp.reason
    return list(by_key.values())


def shortlist(valid: list[Candidate]) -> list[Candidate]:
    """Each agent's top 3 surviving plans by its own round-1 score (ties: lower id). Up to 9, fewer on overlap."""
    picked: dict[str, Candidate] = {}
    for agent in AGENTS:
        own = [c for c in valid if agent in c.r1_scores]
        own.sort(key=lambda c: (-c.r1_scores[agent], int(c.plan_id[1:])))
        for c in own[:SHORTLIST_PER_AGENT]:
            picked.setdefault(c.plan_id, c)
    return sorted(picked.values(), key=lambda c: int(c.plan_id[1:]))


def nash_pick(cands: list[Candidate]) -> Candidate:
    """Highest Pilot x Ground x ATC x cost_score; cost_score = cheapest cost / this cost.
    Ties: lower total cost, then lower plan id."""
    cheapest = min(c.cost_usd for c in cands)
    for c in cands:
        cost_score = 1.0 if c.cost_usd <= 0 else (cheapest / c.cost_usd if cheapest > 0 else 0.0)
        cost_score = max(SCORE_FLOOR, cost_score)
        product = cost_score
        for a in AGENTS:
            product *= c.r2_scores[a]
        c.product = round(product, 6)
    return min(cands, key=lambda c: (-c.product, c.cost_usd, int(c.plan_id[1:])))


class Log:
    """Append-only JSONL consensus log: one line per mediator step."""

    def __init__(self, path: Path, negotiation_id: str):
        self.path, self.negotiation_id = path, negotiation_id
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, round_: int, step: str, **data) -> None:
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "negotiation_id": self.negotiation_id,
                "round": round_, "step": step, **data}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")


async def run_negotiation(agents: dict[str, Agent], check: Callable[[dict], CheckResult],
                          cost: Callable[[dict], float], log: Log, context: dict | None = None) -> Outcome:
    import asyncio

    log.write(0, "scenario", **(context or {}),
              rules={"plans_per_agent": PLANS_PER_AGENT, "shortlist_per_agent": SHORTLIST_PER_AGENT,
                     "score_floor": SCORE_FLOOR,
                     "pick_rule": "max of atc x pilot x ground x cost_score; cost_score = cheapest cost / plan cost; "
                                  "ties: lower cost, then lower id",
                     "consensus_rule": "all three agents accept the picked plan in round 3 and it passes the final check"})

    # ---- Round 1: propose (3 agents in parallel)
    names = list(AGENTS)
    r1 = await asyncio.gather(*(agents[a].propose() for a in names))
    proposals = dict(zip(names, r1))
    for a in names:
        log.write(1, "proposals", agent=a, plans=[asdict(p) for p in proposals[a]])

    cands = merge_duplicates(proposals)
    for c in cands:
        c.check = check(c.plan)
    valid = [c for c in cands if c.check.valid]
    for c in cands:
        log.write(1, "check", plan_id=c.plan_id, proposed_by=c.proposed_by, plan=c.plan,
                  valid=c.check.valid, violations=c.check.violations)
    log.write(1, "filter", received=sum(len(v) for v in proposals.values()), unique=len(cands), valid=len(valid))
    if not valid:
        return _finish(log, "no_valid_plan", None, {}, cands, "No proposed plan passed every hard constraint.")

    short = shortlist(valid)
    for c in short:
        c.cost_usd = round(float(cost(c.plan)), 2)
    log.write(1, "shortlist", plan_ids=[c.plan_id for c in short],
              plans={c.plan_id: {"plan": c.plan, "proposed_by": c.proposed_by, "r1_scores": c.r1_scores,
                                 "r1_reasons": c.r1_reasons, "cost_usd": c.cost_usd} for c in short})

    # ---- Round 2: every agent scores the whole shortlist, seeing the others' round-1 reasons
    table = {c.plan_id: c.plan for c in short}
    reasons = {a: [f"{c.plan_id}: {c.r1_reasons[a]}" for c in short if a in c.r1_reasons] for a in names}
    r2 = await asyncio.gather(*(agents[a].score(table, {o: reasons[o] for o in names if o != a}) for a in names))
    for a, scored in zip(names, r2):
        for c in short:
            sp = scored.get(c.plan_id)
            c.r2_scores[a] = clamp_score(sp.score if sp else None)   # missing score -> floor, logged below
            c.r2_reasons[a] = sp.reason if sp else "no score returned (floored)"
        log.write(2, "scores", agent=a, scores={c.plan_id: [c.r2_scores[a], c.r2_reasons[a]] for c in short})

    best = nash_pick(short)
    log.write(2, "pick", plan_id=best.plan_id, plan=best.plan,
              ranking=[{"plan_id": c.plan_id, "product": c.product, "cost_usd": c.cost_usd, "scores": c.r2_scores}
                       for c in sorted(short, key=lambda c: -c.product)])

    # ---- Round 3: accept / reject the picked plan
    r3 = await asyncio.gather(*(agents[a].vote(best.plan_id, best.plan) for a in names))
    votes = {a: {"accept": v.accept, "reason": v.reason} for a, v in zip(names, r3)}
    log.write(3, "votes", plan_id=best.plan_id, votes=votes)
    final = check(best.plan)                        # last safety check before anything leaves the mediator
    log.write(3, "final_check", plan_id=best.plan_id, valid=final.valid, violations=final.violations)
    if all(v.accept for v in r3) and final.valid:
        return _finish(log, "consensus", best, votes, cands, f"All three agents accepted {best.plan_id}.")
    why = "; ".join(f"{a} rejected: {v['reason']}" for a, v in votes.items() if not v["accept"])
    if not final.valid:
        why = (why + "; " if why else "") + "final check failed: " + "; ".join(final.violations)
    return _finish(log, "no_consensus", best, votes, cands, why + ". Hand over to the human-in-the-loop fallback.")


def _finish(log: Log, outcome: str, best: Candidate | None, votes: dict, cands: list[Candidate],
            why: str) -> Outcome:
    log.write(3, "outcome", outcome=outcome, why=why, plan_id=best.plan_id if best else None,
              plan=best.plan if best else None)
    return Outcome(outcome, best.plan_id if best else None, best.plan if best else None, votes,
                   [asdict(c) for c in cands], str(log.path))
