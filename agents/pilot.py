"""Pilot agent for the focal flight. Priorities, in order: flight safety, fuel, passenger connections.

Architecture: a BDI-style agent communicating with ICAP (Interests, Constraints, Alternatives, Priorities).
Beliefs = facts computed by code (`pilot_facts`); desires = interests; constraints filter feasibility;
priorities rank the feasible alternatives; the intention is the plan it proposes or accepts.

Split (rubric: technical soundness): code computes every number (`assess_plan`, `pilot_alternatives`,
`pilot_concessions`); Claude only weighs those facts, decides, and explains. Code enforces the red lines
after the LLM answers (`_enforce`), so an unsafe accept, or an accept of a plan not on the table, can never
leave this module.

Shared with other agents: the message only (docs/agent-alignment.md). Everything else here is private.
This module adds only the Pilot's role.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import anthropic

from .constraints import ASSUMPTIONS, FuelCrewRules, fuel_crew_rules
from .pilot_inputs import PilotInputs, to_min
from .schema import AgentMessage, Alternative, FailedConstraint, ICAPBrief, Plan, validate_ranges

MODEL = "claude-sonnet-5-5"   # CLAUDE.md section 14: agents on Sonnet tier
EFFORT = "medium"
PROMPT = (Path(__file__).parent / "prompts" / "pilot.md").read_text()

INTERESTS = {
    "weather": "Arrive safely without holding near the weather, keep fuel above the must-divert point, "
               "and get connecting passengers onward.",
    "late_aircraft": "Depart as soon as the late aircraft is ready, without eating into fuel margin, "
                     "and protect onward connections.",
}


# ---------------------------------------------------------------- deterministic assessment (code)
@dataclass(frozen=True)
class FuelBudget:
    spare_min: float                 # holding fuel available on arrival (workbook)
    final_reserve_min: float         # never used (workbook)
    alternate_fuel_min: float        # to fly to the alternate and land
    holdable_before_divert_min: float  # holding possible before the must-divert point
    burn_kg_per_min: float


def fuel_budget(inp: PilotInputs, rules: FuelCrewRules) -> FuelBudget:
    alt_min = inp.alternate.distance_nm / ASSUMPTIONS["cruise_nm_per_min"] + ASSUMPTIONS["alternate_approach_min"]
    burn_h = rules.burn_widebody_kg_h if inp.aircraft_class == "widebody" else rules.burn_narrowbody_kg_h
    return FuelBudget(spare_min=rules.spare_on_arrival_min, final_reserve_min=rules.final_reserve_min,
                      alternate_fuel_min=round(alt_min, 1),
                      holdable_before_divert_min=round(rules.spare_on_arrival_min - alt_min, 1),
                      burn_kg_per_min=round(burn_h / 60, 1))


@dataclass(frozen=True)
class PlanAssessment:
    plan_id: str
    arrival_delay_min: int
    holding_min: int
    holding_fuel_kg: float
    fuel_margin_min: float           # minutes left before the must-divert point (or before reserve if diverting)
    fuel_ok: bool                    # margin >= 0 and final reserve untouched
    minimum_fuel: bool               # margin < 10 min (red line -> flag)
    duty_margin_min: float           # minutes left before the 13-h flight crew duty limit
    duty_ok: bool
    pax_missed: int
    connections_missed: tuple[str, ...]
    last_of_day_missed: tuple[str, ...]
    divert: bool
    binding_constraint: str = "none"     # "fuel" | "crew_duty" | "none"
    evidence: tuple[str, ...] = field(default_factory=tuple)


def assess_plan(plan_id: str, plan: Plan, inp: PilotInputs, rules: FuelCrewRules) -> PlanAssessment:
    fb = fuel_budget(inp, rules)
    arr = to_min(plan.arrival_slot)
    delay = (arr - to_min(inp.sched_arr)) % 1440
    if delay > 720:                      # earlier than scheduled (wrapped)
        delay -= 1440
    if plan.divert:
        # Hold, then fly to the alternate: must reach it with the final reserve intact.
        margin = fb.spare_min + plan.extra_fuel_min - plan.holding_min - fb.alternate_fuel_min
        extra_air = fb.alternate_fuel_min
    else:
        margin = fb.holdable_before_divert_min + plan.extra_fuel_min - plan.holding_min
        extra_air = 0.0
    duty_used = ((to_min(inp.sched_dep) - to_min(inp.crew_report)) % 1440 + plan.ground_delay_min
                 + inp.sched_time_min + plan.holding_min + extra_air)
    duty_margin = rules.flight_crew_max_duty_h * 60 - duty_used
    missed, last_missed, pax = [], [], 0
    if plan.divert:                      # diverting misses every connection at the destination
        missed = [c.flight for c in inp.connections]
        last_missed = [c.flight for c in inp.connections if c.last_of_day]
        pax = sum(c.pax for c in inp.connections)
    else:
        for c in inp.connections:
            if to_min(c.sched_dep) - arr < inp.mct_min:
                missed.append(c.flight)
                pax += c.pax
                if c.last_of_day:
                    last_missed.append(c.flight)
    margin, duty_margin = round(margin, 1), round(duty_margin, 1)
    binding = "fuel" if margin < 0 else "crew_duty" if duty_margin < 0 else "none"
    evidence = (f"plans.{plan_id}.assessment.fuel_margin_min={margin} (must be >= 0)",
                f"fuel.holdable_before_divert_min={fb.holdable_before_divert_min}",
                f"plan.holding_min={plan.holding_min}, plan.extra_fuel_min={plan.extra_fuel_min}",
                f"plans.{plan_id}.assessment.duty_margin_min={duty_margin} (must be >= 0)")
    return PlanAssessment(
        plan_id=plan_id, arrival_delay_min=delay, holding_min=plan.holding_min,
        holding_fuel_kg=round(plan.holding_min * fb.burn_kg_per_min, 0),
        fuel_margin_min=margin, fuel_ok=margin >= 0,
        minimum_fuel=margin < ASSUMPTIONS["minimum_fuel_margin_min"],
        duty_margin_min=duty_margin, duty_ok=duty_margin >= 0,
        pax_missed=pax, connections_missed=tuple(missed), last_of_day_missed=tuple(last_missed),
        divert=plan.divert, binding_constraint=binding, evidence=evidence,
    )


def _rank_key(a: PlanAssessment):
    """Strict priority order among feasible plans (lexicographic, no weights: nothing lower can buy back
    anything higher): avoid diverting, avoid a minimum-fuel margin, avoid stranding last-of-day passengers,
    fewer missed connecting pax, less holding fuel burn."""
    return (a.divert, a.minimum_fuel, len(a.last_of_day_missed), a.pax_missed, a.holding_fuel_kg)


def pilot_red_lines(inp: PilotInputs, rules: FuelCrewRules) -> list[str]:
    """Hard limits stated up front, so ATC and Ground can propose within them. Computed by code."""
    fb = fuel_budget(inp, rules)
    duty_end = (to_min(inp.crew_report) + int(rules.flight_crew_max_duty_h * 60)) % 1440
    return [
        f"Fuel: never plan below the {fb.final_reserve_min:g}-min final reserve",
        f"Holding: at most {fb.holdable_before_divert_min} min without extra fuel; beyond that, divert to "
        f"{inp.alternate.iata} ({fb.alternate_fuel_min} min away)",
        f"Minimum fuel declared if margin falls below {ASSUMPTIONS['minimum_fuel_margin_min']:g} min",
        f"Crew duty: block-in by {duty_end // 60:02d}:{duty_end % 60:02d} {inp.origin} time "
        f"({rules.flight_crew_max_duty_h:g} h from report {inp.crew_report})",
    ]


def pilot_alternatives(inp: PilotInputs, plans: dict[str, Plan], rules: FuelCrewRules) -> list[dict]:
    """Safe alternatives generated by code from each candidate, ranked by the Pilot's priorities.
    All are 'candidate': ATC (slot) and Ground (gate) have not confirmed them."""
    fb = fuel_budget(inp, rules)
    buffer = ASSUMPTIONS["minimum_fuel_margin_min"]
    variants: dict[str, Plan] = {}
    for pid, p in plans.items():
        variants[pid] = p
        if p.holding_min > 0 and not inp.airborne:      # absorb the delay on the ground instead
            variants[f"{pid}-ground-delay"] = p.model_copy(update={
                "ground_delay_min": p.ground_delay_min + p.holding_min, "holding_min": 0, "extra_fuel_min": 0})
        if not p.divert and not inp.airborne:            # load enough extra fuel to hold safely
            need = math.ceil(p.holding_min + buffer - fb.holdable_before_divert_min)
            if need > p.extra_fuel_min:
                variants[f"{pid}-extra-fuel"] = p.model_copy(update={"extra_fuel_min": need})
        if not p.divert:                                 # divert now, instead of holding
            variants[f"{pid}-divert"] = p.model_copy(update={"divert": True, "holding_min": 0})
    assessed = [(vid, v, assess_plan(vid, v, inp, rules)) for vid, v in variants.items()]
    safe = sorted([x for x in assessed if x[2].fuel_ok and x[2].duty_ok], key=lambda x: _rank_key(x[2]))
    if any(not a.divert for _, _, a in safe):           # divert only listed when nothing else is safe
        safe = [x for x in safe if not x[2].divert]
    return [{"plan_ref": vid, "plan": v.model_dump(), "status": "candidate",
             "summary": (f"{'divert to ' + inp.alternate.iata if a.divert else 'arrive ' + v.arrival_slot}, "
                         f"ground delay {v.ground_delay_min} min, holding {v.holding_min} min, extra fuel "
                         f"{v.extra_fuel_min} min; fuel margin {a.fuel_margin_min} min; {a.pax_missed} pax miss connections"),
             "assessment": asdict(a)} for vid, v, a in safe]


def pilot_concessions(inp: PilotInputs, best: PlanAssessment | None) -> list[str]:
    """Lower-priority items the Pilot can give up. Never a safety item."""
    out = []
    if best is not None and best.duty_margin_min > 30:
        out.append(f"Accept up to {int(min(best.duty_margin_min - 30, 120))} min more ground delay (crew duty margin)")
    for c in inp.connections:
        if not c.last_of_day:
            out.append(f"Can give up connection {c.flight} to {c.to} ({c.pax} pax; a later flight exists)")
    out.append("A gate change is acceptable if it does not cause more missed connections")
    return out


def decision_deadline(inp: PilotInputs, rules: FuelCrewRules) -> str:
    fb = fuel_budget(inp, rules)
    if inp.airborne:
        return f"Must divert to {inp.alternate.iata} after {fb.holdable_before_divert_min} min of holding (plus any extra fuel)"
    return f"Decide extra fuel before scheduled departure {inp.sched_dep} local; holding beyond " \
           f"{fb.holdable_before_divert_min} min needs extra fuel or a ground delay"


def pilot_facts(inp: PilotInputs, plans: dict[str, Plan], rules: FuelCrewRules | None = None) -> dict:
    """The Pilot's private view: only its own facts, every number computed by code, provenance labelled."""
    rules = rules or fuel_crew_rules()
    fb = fuel_budget(inp, rules)
    alternatives = pilot_alternatives(inp, plans, rules)
    best = PlanAssessment(**{k: tuple(v) if isinstance(v, list) else v
                             for k, v in alternatives[0]["assessment"].items()}) if alternatives else None
    return {
        "flight": {"id": inp.flight, "tail": inp.tail, "route": f"{inp.origin}->{inp.dest}", "date": inp.date,
                   "sched_dep_local": inp.sched_dep, "sched_arr_local": inp.sched_arr,
                   "sched_block_min": inp.sched_time_min, "aircraft_class": inp.aircraft_class,
                   "airborne": inp.airborne, "provenance": "real schedule (flights.csv); class by distance rule"},
        "event": {"type": inp.event_type, "reported_cause_min": inp.event_magnitude_min,
                  "note": "weather at destination: airborne holding is near the weather; ground delay avoids it"
                  if inp.event_type == "weather" else "late inbound aircraft: departure readiness is late"},
        "interest": INTERESTS[inp.event_type],
        "red_lines": pilot_red_lines(inp, rules),
        "fuel": {**asdict(fb), "rule_source": rules.source,
                 "minimum_fuel_margin_min": ASSUMPTIONS["minimum_fuel_margin_min"]},
        "alternate": asdict(inp.alternate),
        "crew": {"report_local": inp.crew_report, "max_duty_h": rules.flight_crew_max_duty_h,
                 "provenance": "derived: tail's earliest delayed leg that day minus 60 min (approximate)"},
        "connections": {"mct_min": inp.mct_min, "list": [asdict(c) for c in inp.connections]},
        "plans": {pid: {"plan": p.model_dump(), "assessment": asdict(assess_plan(pid, p, inp, rules))}
                  for pid, p in plans.items()},
        "alternatives": alternatives,
        "concessions": pilot_concessions(inp, best),
        "deadline": decision_deadline(inp, rules),
    }


# ---------------------------------------------------------------- agent (Claude)
class PilotAgent:
    """Async: the middleman runs the three agents concurrently each round, e.g.
    `await asyncio.gather(atc.respond(...), pilot.respond(...), ground.respond(...))`."""

    def __init__(self, client: anthropic.AsyncAnthropic | None = None, model: str = MODEL, effort: str = EFFORT,
                 dry_run: bool = False):
        self.dry_run = dry_run
        self.client = None if dry_run else (client or anthropic.AsyncAnthropic())
        self.model, self.effort = model, effort
        self.calls: list[dict] = []      # per-call log for the consensus log / evaluation

    async def propose(self, inp: PilotInputs, candidates: dict[str, Plan], round_: int = 1) -> AgentMessage:
        facts = pilot_facts(inp, candidates)
        task = ("Round 1. Assess the candidate plans in `plans` and the code-generated `alternatives`, then propose "
                "the plan you want on the table (action 'propose', include the full plan). Prefer the top-ranked "
                "alternative unless a fact in FACTS argues otherwise. Fill `icap`.")
        return await self._run(inp, facts, task, round_, candidates)

    async def respond(self, inp: PilotInputs, table_id: str, table: Plan, checker: dict, others: list[dict],
                round_: int) -> AgentMessage:
        facts = pilot_facts(inp, {table_id: table})
        task = (f"Round {round_}. The plan on the table is {table_id}. Constraint checker result: "
                f"{json.dumps(checker)}. Other agents' latest messages: {json.dumps(others)}. "
                f"Check {table_id} against your own facts even if others prefer it. Reply with 'accept' "
                f"(plan_id={table_id}, this exact plan only), 'counter' (include your full counter-plan, "
                "ideally from `alternatives`), or 'reject'. Fill `icap`.")
        return await self._run(inp, facts, task, round_, {table_id: table})

    # -- internals
    async def _run(self, inp, facts, task, round_, plans) -> AgentMessage:
        msg = self._policy(inp, facts, round_) if self.dry_run else await self._ask_claude(facts, task, round_)
        return self._enforce(msg, inp, round_, plans)

    async def _ask_claude(self, facts: dict, task: str, round_: int) -> AgentMessage:
        messages = [{"role": "user", "content": f"FACTS (computed by code):\n{json.dumps(facts, indent=1)}\n\nTASK: {task}"}]
        for attempt in (1, 2):           # re-ask once, then treat as reject (CLAUDE.md section 5)
            try:
                resp = await self.client.messages.parse(
                    model=self.model, max_tokens=4000,
                    system=[{"type": "text", "text": PROMPT, "cache_control": {"type": "ephemeral"}}],
                    messages=messages, output_format=AgentMessage, output_config={"effort": self.effort},
                )
            except anthropic.APIConnectionError as e:
                self.calls.append({"attempt": attempt, "error": f"connection: {e}"})
                continue
            except anthropic.RateLimitError as e:
                self.calls.append({"attempt": attempt, "error": f"rate_limited: {e.message}"})
                continue
            except anthropic.APIStatusError as e:
                self.calls.append({"attempt": attempt, "error": f"api_{e.status_code}: {e.message}"})
                break
            self.calls.append({"attempt": attempt, "request_id": resp._request_id, "stop_reason": resp.stop_reason,
                               "usage": resp.usage.model_dump()})
            if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
                messages.append({"role": "user", "content": f"Your last reply could not be used "
                                 f"(stop_reason={resp.stop_reason}). Reply again with one valid message."})
                continue
            msg = resp.parsed_output
            problems = validate_ranges(msg)
            if not problems:
                return msg
            messages += [{"role": "assistant", "content": msg.model_dump_json(by_alias=True)},
                         {"role": "user", "content": f"Fix these problems and reply again: {problems}"}]
        return AgentMessage(**{"from": "pilot"}, round=round_, action="reject", need="a valid plan",
                            offer="none", reason="Pilot agent output invalid twice; treated as reject.")

    def _policy(self, inp: PilotInputs, facts: dict, round_: int) -> AgentMessage:
        """Deterministic stand-in for Claude (dry-run / tests): same priority order and ICAP brief as the prompt."""
        alts = facts["alternatives"]
        icap_alts = [Alternative(plan_ref=a["plan_ref"], summary=a["summary"], status="candidate") for a in alts[:3]]
        if not alts:
            return AgentMessage(**{"from": "pilot"}, round=round_, action="reject", need="more fuel or a later slot",
                                offer="ground delay", reason="Every plan breaks fuel or duty limits (fuel.holdable_before_divert_min).",
                                icap=ICAPBrief(interest=facts["interest"], deadline=facts["deadline"],
                                               concessions=facts["concessions"],
                                               requested_next_action="ATC: later slot with ground delay"))
        top = alts[0]
        a = top["assessment"]
        on_table = round_ > 1 and top["plan_ref"] in facts["plans"]
        if round_ == 1:
            action, plan_id, plan = "propose", None, Plan(**top["plan"])
        elif on_table:
            action, plan_id, plan = "accept", top["plan_ref"], None
        else:
            action, plan_id, plan = "counter", None, Plan(**top["plan"])
        return AgentMessage(
            **{"from": "pilot"}, round=round_, action=action, plan_id=plan_id, plan=plan,
            need="ATC confirm slot; Ground confirm gate" if action != "accept" else "none",
            offer="accept ground delay instead of airborne holding",
            reason=f"Top safe alternative {top['plan_ref']}: fuel margin {a['fuel_margin_min']} min, {a['pax_missed']} pax missed.",
            icap=ICAPBrief(interest=facts["interest"], alternatives=icap_alts, concessions=facts["concessions"],
                           deadline=facts["deadline"],
                           requested_next_action="ATC confirm slot, Ground confirm gate" if action != "accept" else "proceed"))

    def _enforce(self, msg: AgentMessage, inp: PilotInputs, round_: int, plans: dict[str, Plan]) -> AgentMessage:
        """Red lines in code: never accept a plan not on the table, never accept/propose an unsafe plan.
        Safety flags are code-derived regardless of what the LLM wrote."""
        rules = fuel_crew_rules()
        msg = msg.model_copy(update={"from_": "pilot", "round": round_})
        icap = msg.icap or ICAPBrief(interest=INTERESTS[inp.event_type], requested_next_action="see need")
        icap = icap.model_copy(update={"red_lines": pilot_red_lines(inp, rules)})   # code-derived, always stated
        if msg.action == "accept" and msg.plan_id not in plans:
            return msg.model_copy(update={
                "action": "reject", "plan_id": None, "plan": None, "need": "confirm the plan id and version on the table",
                "reason": f"Code override: accepted plan_id {msg.plan_id!r} is not the plan on the table {sorted(plans)}.",
                "icap": icap.model_copy(update={"requested_next_action": "Middleman: resend the current table plan"})})
        if msg.action in ("counter", "reject") and icap.failed_constraint is None:
            for pid, p in plans.items():          # record, from code, why the table plan was unacceptable
                ta = assess_plan(pid, p, inp, rules)
                if ta.binding_constraint != "none":
                    icap = icap.model_copy(update={"failed_constraint": FailedConstraint(
                        rule=ta.binding_constraint, evidence=list(ta.evidence))})
                    break
        chosen = msg.plan if msg.action in ("propose", "counter") else plans.get(msg.plan_id or "")
        if chosen is None:
            return msg.model_copy(update={"icap": icap, "flags": []})
        a = assess_plan(msg.plan_id or "own", chosen, inp, rules)
        flags = set()                     # safety flags are code-derived only; LLM-supplied flags are dropped
        if a.minimum_fuel:
            flags.add("MINIMUM_FUEL")
        if not a.duty_ok:
            flags.add("DUTY_LIMIT")
        alts = pilot_alternatives(inp, plans, rules)
        if alts and alts[0]["assessment"]["divert"]:
            flags.add("DIVERT_RECOMMENDED")
        if msg.action != "reject" and (not a.fuel_ok or not a.duty_ok):
            failed = FailedConstraint(rule="fuel" if not a.fuel_ok else "crew_duty", evidence=list(a.evidence))
            return msg.model_copy(update={
                "action": "reject", "plan_id": None, "plan": None, "flags": sorted(flags),
                "reason": f"Code override: plan breaks {'fuel' if not a.fuel_ok else 'crew duty'} limit "
                          f"(fuel margin {a.fuel_margin_min} min, duty margin {a.duty_margin_min} min).",
                "icap": icap.model_copy(update={
                    "failed_constraint": failed,
                    "alternatives": [Alternative(plan_ref=x["plan_ref"], summary=x["summary"], status="candidate")
                                     for x in alts[:3]]})})
        return msg.model_copy(update={"flags": sorted(flags), "icap": icap})
