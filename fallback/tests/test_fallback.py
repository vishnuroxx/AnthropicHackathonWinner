"""Fallback solver tests: determinism, cancel path, fuel rule, re-check, no hindsight."""
import json
from dataclasses import fields, replace

import pytest

from fallback import build_world, solve
from fallback.config import HINDSIGHT_COLUMNS
from fallback.rules import check
from fallback.world import Alternate

from atc_agent.world_stub import load_day, pick_focal  # noqa: E402 (sys.path set by fallback.world)


@pytest.fixture(scope="module")
def rows():
    return load_day(2015, 4, 24)


@pytest.fixture(scope="module")
def world(rows):
    return build_world(rows, pick_focal(rows, "DFW"), seed=0)


def test_deterministic(world, rows):
    a, b = solve(world, "baseline"), solve(world, "baseline")
    assert a == b and json.dumps(a) == json.dumps(b)
    again = solve(build_world(rows, pick_focal(rows, "DFW"), seed=0), "baseline")
    assert json.dumps(a) == json.dumps(again)


def test_all_blocked_recommends_cancel(world):
    blocked = replace(world, gate_busy={g: ((0, 10**6),) for g in world.gates},
                      alternate=Alternate("XXX", "too far", 5000.0))
    out = solve(blocked, "no_valid_r1")
    assert out["outcome"] == "recommend_cancel" and out["plan"] is None
    assert out["fallback"]["valid"] == 0 and out["fallback"]["rejected_by_rule"]["C-FUEL-1"] > 0


def test_holding_beyond_holdable_is_invalid(world):
    slot = "%02d:%02d" % divmod(world.earliest_arr_min + 60, 60)
    plan = {"arrival_slot": slot, "ground_delay_min": 0, "holding_min": world.holdable_min + 15,
            "extra_fuel_min": 0, "gate": world.gates[1], "divert": False}
    res = check(plan, world)
    assert not res["valid"] and any(v.startswith("C-FUEL-1") for v in res["violations"])
    assert check(plan | {"extra_fuel_min": 15}, world)["flags"] == ["MINIMUM_FUEL"]  # margin 0 < 10 min


def test_chosen_plan_rechecks_valid(world):
    out = solve(world, "no_consensus_r3")
    assert out["outcome"] == "halt_least_cost" and out["fallback"]["valid"] > 0
    again = check(out["plan"], world)
    assert again["valid"] and again["status"] == "VALID"
    assert all(c["result"] == "PASS" for c in again["checks"])
    assert out["plan"]["holding_min"] <= world.holdable_min + out["plan"]["extra_fuel_min"]


def test_world_has_no_hindsight(rows):
    focal = pick_focal(rows, "DFW")
    assert not {f.name.upper() for f in fields(build_world(rows, focal))} & HINDSIGHT_COLUMNS
    poisoned = [{k: ("9999" if k in HINDSIGHT_COLUMNS else v) for k, v in r.items()} for r in rows]
    p_focal = pick_focal(poisoned, "DFW")
    w1, w2 = build_world(rows, focal, 0), build_world(poisoned, p_focal, 0)
    assert all(getattr(w1, f.name) == getattr(w2, f.name) for f in fields(w1))
