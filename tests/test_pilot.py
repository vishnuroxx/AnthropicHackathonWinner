"""Pilot agent tests. No API calls (dry-run policy). Run: .venv/bin/python -m tests.test_pilot"""
import asyncio
import csv
import time
from types import SimpleNamespace

from agents.constraints import fuel_crew_rules
from agents.pilot import (PilotAgent, assess_plan, fuel_budget, pilot_alternatives, pilot_concessions,
                          pilot_facts)
from agents.pilot_inputs import FLIGHTS, Alternate, Connection, PilotInputs, build_pilot_inputs
from agents.schema import AgentMessage, Plan

RULES = fuel_crew_rules()

INP = PilotInputs(
    flight="AA100", tail="N1AA", origin="ORD", dest="DFW", date="2015-04-24", sched_dep="15:00",
    sched_arr="17:30", sched_time_min=150, distance_mi=802, aircraft_class="narrowbody",
    event_type="weather", event_magnitude_min=40, airborne=False,
    alternate=Alternate("DAL", "Dallas Love Field", 120.0), crew_report="06:00", mct_min=45,
    connections=(Connection("AA200", "AUS", "18:30", 12, False), Connection("AA300", "ELP", "19:00", 20, True)),
)


def plan(slot, gd=0, hold=0, extra=0, divert=False):
    return Plan(arrival_slot=slot, ground_delay_min=gd, holding_min=hold, extra_fuel_min=extra, gate="C14", divert=divert)


def test_workbook_values():
    assert RULES.final_reserve_min == 30 and RULES.spare_on_arrival_min == 45
    assert RULES.burn_narrowbody_kg_h == 2400 and RULES.flight_crew_max_duty_h == 13


def test_fuel_budget():
    fb = fuel_budget(INP, RULES)
    assert fb.alternate_fuel_min == round(120 / 7 + 10, 1)          # 27.1
    assert fb.holdable_before_divert_min == round(45 - (120 / 7 + 10), 1)
    assert fb.burn_kg_per_min == 40.0


def test_holding_beyond_divert_point_is_unsafe_and_extra_fuel_fixes_it():
    bad = assess_plan("P1", plan("17:55", hold=25), INP, RULES)       # 17.9 min holdable
    assert not bad.fuel_ok and bad.minimum_fuel
    ok = assess_plan("P2", plan("17:55", hold=25, extra=20), INP, RULES)
    assert ok.fuel_ok and ok.fuel_margin_min == round(45 - (120 / 7 + 10) + 20 - 25, 1)


def test_connections_and_last_of_day():
    a = assess_plan("P3", plan("18:10", gd=40), INP, RULES)            # AA200: 20 min < 45 MCT; AA300: 50 min OK
    assert a.connections_missed == ("AA200",) and a.pax_missed == 12 and a.last_of_day_missed == ()
    b = assess_plan("P4", plan("18:30", gd=60), INP, RULES)            # misses both
    assert b.pax_missed == 32 and b.last_of_day_missed == ("AA300",)


def test_duty_limit():
    late_report = PilotInputs(**{**INP.__dict__, "crew_report": "03:00"})   # 12 h before dep
    a = assess_plan("P5", plan("19:30", gd=120), late_report, RULES)
    assert not a.duty_ok


def test_dry_run_prefers_safe_ground_delay_over_unsafe_holding():
    agent = PilotAgent(dry_run=True)
    cands = {"P1": plan("17:55", hold=25), "P2": plan("17:55", gd=25), "P3": plan("18:30", gd=60)}
    msg = asyncio.run(agent.propose(INP, cands))
    assert msg.action == "propose" and msg.plan.ground_delay_min == 25 and msg.plan.holding_min == 0


def test_code_override_blocks_unsafe_accept():
    agent = PilotAgent(dry_run=True)
    unsafe = plan("17:55", hold=25)
    llm_says_accept = AgentMessage(**{"from": "pilot"}, round=2, action="accept", plan_id="P1",
                                   need="-", offer="-", reason="looks fine")
    msg = agent._enforce(llm_says_accept, INP, 2, {"P1": unsafe})
    assert msg.action == "reject" and "MINIMUM_FUEL" in msg.flags and msg.reason.startswith("Code override")


def test_accept_of_plan_not_on_table_is_rejected():
    agent = PilotAgent(dry_run=True)
    stale = AgentMessage(**{"from": "pilot"}, round=3, action="accept", plan_id="P2",
                         need="-", offer="-", reason="accepting earlier version")
    msg = agent._enforce(stale, INP, 3, {"P2b": plan("18:10", gd=40)})
    assert msg.action == "reject" and "not the plan on the table" in msg.reason


def test_alternatives_turn_unsafe_holding_into_safe_candidates():
    alts = pilot_alternatives(INP, {"P1": plan("17:55", hold=25)}, RULES)
    refs = [a["plan_ref"] for a in alts]
    assert "P1" not in refs                                   # unsafe original excluded
    assert "P1-ground-delay" in refs and "P1-extra-fuel" in refs
    assert refs[0] == "P1-ground-delay"                       # no holding fuel burn ranks first
    assert all(a["status"] == "candidate" and a["assessment"]["fuel_ok"] for a in alts)
    assert not any(a["assessment"]["divert"] for a in alts)   # divert only when nothing else is safe


def test_divert_offered_only_when_nothing_else_is_safe():
    airborne = PilotInputs(**{**INP.__dict__, "airborne": True})
    alts = pilot_alternatives(airborne, {"P1": plan("17:55", hold=25)}, RULES)
    assert alts and alts[0]["assessment"]["divert"]


def test_concessions_never_include_safety():
    best = assess_plan("P2", plan("17:55", gd=25), INP, RULES)
    c = pilot_concessions(INP, best)
    assert any("AA200" in x for x in c) and not any("AA300" in x for x in c)   # AA300 is last of day
    assert not any(w in " ".join(c).lower() for w in ("reserve", "fuel margin", "duty limit"))


def test_dry_run_and_override_carry_icap():
    agent = PilotAgent(dry_run=True)
    msg = asyncio.run(agent.propose(INP, {"P1": plan("17:55", hold=25), "P3": plan("18:30", gd=60)}))
    assert msg.icap and msg.icap.interest and msg.icap.alternatives and msg.icap.deadline
    assert msg.icap.alternatives[0].status == "candidate"
    over = agent._enforce(AgentMessage(**{"from": "pilot"}, round=2, action="accept", plan_id="P1",
                                       need="-", offer="-", reason="ok"), INP, 2, {"P1": plan("17:55", hold=25)})
    assert over.icap.failed_constraint.rule == "fuel"
    assert any("fuel_margin_min=" in e for e in over.icap.failed_constraint.evidence)


def test_llm_supplied_safety_flag_is_dropped_when_code_disagrees():
    # Live run: Claude flagged MINIMUM_FUEL on a counter-plan with an 18.3-min margin (threshold 10).
    agent = PilotAgent(dry_run=True)
    llm = AgentMessage(**{"from": "pilot"}, round=2, action="counter", plan=plan("17:55", gd=25),
                       need="-", offer="-", reason="P1 fails fuel", flags=["MINIMUM_FUEL"])
    msg = agent._enforce(llm, INP, 2, {"P1": plan("17:55", hold=25)})
    assert msg.action == "counter" and msg.flags == []
    assert msg.icap.failed_constraint.rule == "fuel"          # the table plan's failure is still recorded


def test_red_lines_stated_up_front_and_code_derived():
    agent = PilotAgent(dry_run=True)
    llm = AgentMessage(**{"from": "pilot"}, round=2, action="accept", plan_id="P1", need="-", offer="-",
                       reason="ok")                                     # Claude stated no red lines
    msg = agent._enforce(llm, INP, 2, {"P1": plan("17:40", gd=10)})    # safe plan, nothing fails
    rl = " | ".join(msg.icap.red_lines)
    assert msg.action == "accept" and "30-min final reserve" in rl
    assert "17.9 min without extra fuel" in rl and "DAL" in rl         # holdable before divert, alternate
    assert "block-in by 19:00 ORD time" in rl                           # 06:00 report + 13 h


def test_rank_key_puts_last_of_day_before_pax_count():
    from agents.pilot import _rank_key
    base = assess_plan("X", plan("17:40", gd=10), INP, RULES)
    strands_last = base.__class__(**{**base.__dict__, "pax_missed": 5, "last_of_day_missed": ("AA300",)})
    misses_more = base.__class__(**{**base.__dict__, "pax_missed": 40, "last_of_day_missed": ()})
    assert _rank_key(misses_more) < _rank_key(strands_last)


class _SlowFakeMessages:
    """Fake async client: every call takes 0.3 s and returns a valid counter (no network)."""
    async def parse(self, **kw):
        await asyncio.sleep(0.3)
        msg = AgentMessage(**{"from": "pilot"}, round=2, action="counter", plan=plan("17:55", gd=25),
                           need="ATC confirm slot", offer="ground delay", reason="fuel")
        return SimpleNamespace(parsed_output=msg, stop_reason="end_turn", _request_id="fake",
                               usage=SimpleNamespace(model_dump=lambda: {}))


def test_agents_run_concurrently_not_sequentially():
    fake = SimpleNamespace(messages=_SlowFakeMessages())
    agents = [PilotAgent(client=fake) for _ in range(3)]       # stand-ins for ATC, Pilot, Ground

    async def one_round():
        return await asyncio.gather(*(a.respond(INP, "P1", plan("17:55", hold=25), {"valid": True}, [], 2)
                                      for a in agents))
    t0 = time.perf_counter()
    replies = asyncio.run(one_round())
    elapsed = time.perf_counter() - t0
    assert len(replies) == 3 and all(r.action == "counter" for r in replies)
    assert elapsed < 0.6, f"calls ran sequentially ({elapsed:.2f}s for 3 x 0.3s)"


def test_real_row_dfw_demo_day():
    with open(FLIGHTS, newline="") as f:
        row = next(r for r in csv.DictReader(f) if r["MONTH"] == "4" and r["DAY"] == "24"
                   and r["DESTINATION_AIRPORT"] == "DFW" and float(r["WEATHER_DELAY"] or 0) > 15)
    inp = build_pilot_inputs(row, seed=7)
    assert inp.event_type == "weather" and inp.alternate.iata != "DFW" and inp.alternate.distance_nm > 100
    facts = pilot_facts(inp, {"P1": plan(inp.sched_arr, gd=0)})
    for leaked in ("ARRIVAL_DELAY", "DEPARTURE_TIME", "ARRIVAL_TIME", "AIR_TIME"):
        assert leaked not in str(facts), f"hindsight column leaked: {leaked}"
    print(f"  real row: {inp.flight} {inp.origin}->{inp.dest} sched_arr {inp.sched_arr}, alternate "
          f"{inp.alternate.iata} {inp.alternate.distance_nm} nm, crew report {inp.crew_report}, "
          f"{len(inp.connections)} connections")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
