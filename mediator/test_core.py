"""Mediator core tests (pure code, no API). Run: .venv/bin/python -m mediator.test_core"""
import asyncio
import tempfile
from pathlib import Path

from mediator.core import (SCORE_FLOOR, Candidate, CheckResult, Log, ScoredPlan, Vote, merge_duplicates,
                           nash_pick, run_negotiation, shortlist)


def plan(slot, gate="B1", gd=0, hold=0):
    return {"arrival_slot": slot, "ground_delay_min": gd, "holding_min": hold, "extra_fuel_min": 0,
            "gate": gate, "divert": False}


def test_merge_keeps_every_proposer():
    c = merge_duplicates({"atc": [ScoredPlan(plan("20:00"), 0.9, "a")],
                          "pilot": [ScoredPlan(plan("20:00"), 0.4, "p"), ScoredPlan(plan("20:10"), 1.0, "p2")]})
    assert len(c) == 2 and c[0].proposed_by == ["atc", "pilot"]
    assert c[0].r1_scores == {"atc": 0.9, "pilot": 0.4}


def test_shortlist_top3_per_agent_dedupes_overlap():
    cands = [Candidate(f"C{i}", plan(f"20:{i:02d}"), ["atc"], {"atc": 1 - i / 10}) for i in range(1, 6)]
    cands[0].r1_scores["pilot"] = 1.0
    ids = [c.plan_id for c in shortlist(cands)]
    assert ids == ["C1", "C2", "C3"]                 # pilot's top plan C1 is already in ATC's top 3


def test_nash_balanced_plan_beats_lopsided_one():
    a = Candidate("C1", plan("20:00"), [], cost_usd=4000, r2_scores={"atc": 0.9, "pilot": 0.9, "ground": 0.2})
    b = Candidate("C2", plan("20:10"), [], cost_usd=4000, r2_scores={"atc": 0.6, "pilot": 0.6, "ground": 0.7})
    assert nash_pick([a, b]).plan_id == "C2"          # 0.162 vs 0.252


def test_nash_cost_factor_and_floor():
    cheap = Candidate("C1", plan("20:00"), [], cost_usd=4000, r2_scores={"atc": 0.9, "pilot": 0.2, "ground": 0.9})
    dear = Candidate("C2", plan("20:10"), [], cost_usd=6500, r2_scores={"atc": 0.6, "pilot": 0.6, "ground": 0.7})
    assert nash_pick([cheap, dear]).plan_id == "C1"   # 0.162 vs 0.252 * 4000/6500 = 0.155
    zero = Candidate("C3", plan("20:20"), [], cost_usd=4000, r2_scores={"atc": SCORE_FLOOR, "pilot": 1, "ground": 1})
    nash_pick([zero])
    assert zero.product > 0                           # floored, not a veto


class FakeAgent:
    def __init__(self, name, plans, accept=True):
        self.name, self.plans, self.accept = name, plans, accept

    async def propose(self):
        return [ScoredPlan(p, s, f"{self.name} likes it") for p, s in self.plans]

    async def score(self, table, others):
        assert all(self.name not in k for k in others)    # sees only the OTHER agents' reasons
        return {pid: ScoredPlan(p, dict((plan_key, s) for plan_key, s in
                                        ((tuple(sorted(q.items())), s) for q, s in self.plans)).get(
                                            tuple(sorted(p.items())), 0.5), "r2") for pid, p in table.items()}

    async def vote(self, plan_id, p):
        return Vote(self.accept, "ok" if self.accept else "no")


def _run(agents, invalid_slots=()):
    check = lambda p: CheckResult(p["arrival_slot"] not in invalid_slots,   # noqa: E731
                                  [] if p["arrival_slot"] not in invalid_slots else ["C-FUEL-1: test"])
    with tempfile.TemporaryDirectory() as d:
        return asyncio.run(run_negotiation(agents, check, lambda p: 1000.0, Log(Path(d) / "l.jsonl", "T")))


def test_end_to_end_consensus_and_invalid_plans_never_reach_round_2():
    shared, bad = plan("20:10"), plan("20:00")
    agents = {"atc": FakeAgent("atc", [(bad, 1.0), (shared, 0.8)]),
              "pilot": FakeAgent("pilot", [(shared, 1.0)]),
              "ground": FakeAgent("ground", [(shared, 0.9)])}
    out = _run(agents, invalid_slots={"20:00"})
    assert out.outcome == "consensus" and out.plan == shared


def test_any_reject_means_no_consensus():
    p = plan("20:10")
    agents = {n: FakeAgent(n, [(p, 1.0)], accept=(n != "ground")) for n in ("atc", "pilot", "ground")}
    out = _run(agents)
    assert out.outcome == "no_consensus" and out.votes["ground"]["accept"] is False


def test_no_valid_plan():
    agents = {n: FakeAgent(n, [(plan("20:00"), 1.0)]) for n in ("atc", "pilot", "ground")}
    assert _run(agents, invalid_slots={"20:00"}).outcome == "no_valid_plan"


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
