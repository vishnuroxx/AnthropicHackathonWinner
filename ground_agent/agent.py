"""Ground Ops agent: separate system prompt, one call per round, only Ground's facts.

The model decides only the gate (GroundDecision) plus short text. Code assembles the shared
AgentMessage (agents/schema.py): the full Plan, the safety flags, and the ICAP brief (interest,
concessions, deadline, failed constraint). An accept of a plan that is not on the table, or that
fails the Ground check, is overridden to `reject` in code (same pattern as the Pilot agent).
Invalid output is re-asked once, then becomes `reject`.
"""
import json
import time
from pathlib import Path
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, ValidationError

from agents.schema import AgentMessage, Alternative, FailedConstraint, ICAPBrief, Plan, validate_ranges
from ground_agent.assumptions import LIMITS_SOURCE, MAX_GATE_WAIT_MIN, OVERTIME_MULTIPLIER
from ground_agent.checker import GroundCheck, check_ground
from ground_agent.cost import cost_ground
from ground_agent.icap import build_icap
from ground_agent.inputs import WorldState, walk_min
from ground_agent.options import free_gate_ids
from ground_agent.timeutil import min_to_hhmm

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 4000
EFFORT = "medium"
PROMPT_PATH = Path(__file__).parent / "prompts" / "ground.md"
# Outcome columns agents must never see (CLAUDE.md section 6, "No hindsight").
FORBIDDEN_FIELDS = {
    "departure_time", "arrival_time", "arrival_delay", "departure_delay",
    "wheels_on", "wheels_off", "elapsed_time", "air_time", "taxi_in", "taxi_out",
}
INTERESTS = {
    "weather": "Land onto a free gate with no wait, keep the turnaround at the airport minimum "
               "and the crew inside its shift.",
    "late_aircraft": "Protect the next departure: turnaround at the airport minimum, no crew overtime, "
                     "gate ready when the aircraft is.",
}


class GroundDecision(BaseModel):
    """What the model returns: Ground's one lever (the gate) plus the short text fields."""
    action: Literal["propose", "accept", "counter", "reject"]
    plan_id: Optional[str] = None
    gate: str
    interests_cited: list[str]
    need: str
    offer: str
    reason: str
    requested_next_action: str


# Raises if any outcome ("hindsight") column name appears as a key anywhere in obj.
# Args: obj - nested dict/list to scan.
# Returns: None.
# Raises: ValueError naming the forbidden field.
def assert_no_hindsight(obj) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_FIELDS:
                raise ValueError(f"hindsight field {k!r} must not reach an agent")
            assert_no_hindsight(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_hindsight(v)


# Builds Ground's private facts for the prompt. Code-computed; nothing from ATC/Pilot.
# Args: state - world state.
# Returns: JSON-serialisable dict.
# Raises: ValueError if a hindsight field slipped in.
def build_ground_facts(state: WorldState) -> dict:
    icap = build_icap(state)
    free_gates = [
        {"gate": g, "terminal": g[0], "walk_min_from_scheduled_gate": walk_min(state.scheduled_gate, g)}
        for g in free_gate_ids(state)
    ]
    confirm_by = min_to_hhmm(state.disrupted_arrival_min - state.gate_change_notice_min)
    facts = {
        "airport": state.airport,
        "limits": {
            "gates": state.limits.gates, "min_turnaround_min": state.limits.min_turnaround_min,
            "spare_gates_at_any_time": state.limits.spare_gates_at_any_time, "source": LIMITS_SOURCE,
        },
        "rules": {
            "gate_change_notice_min": state.gate_change_notice_min, "max_gate_wait_min": MAX_GATE_WAIT_MIN,
            "crew_shift_min": state.crew_shift_min, "crew_overtime_multiplier": OVERTIME_MULTIPLIER,
        },
        "event": {"type": state.event_type, "magnitude_min": state.event_magnitude_min},
        "focal_flight": {
            "flight": state.focal_flight, "tail": state.tail,
            "scheduled_arrival": min_to_hhmm(state.scheduled_arrival_min),
            "disrupted_arrival": min_to_hhmm(state.disrupted_arrival_min),
            "next_departure": min_to_hhmm(state.next_departure_min),
            "connecting_pax": state.connecting_pax, "connection_slack_min": state.connection_slack_min,
        },
        "announced_at": min_to_hhmm(state.now_min),
        "scheduled_gate": state.scheduled_gate,
        "scheduled_gate_busy": [
            {"from": min_to_hhmm(w.start), "until": min_to_hhmm(w.end), "label": w.label}
            for w in state.gate_busy[state.scheduled_gate]
        ],
        "free_gates": free_gates,
        "crew_shift_end": min_to_hhmm(state.crew_shift_end_min),
        "interest": INTERESTS[state.event_type],
        "concessions": [
            f"Wait up to {MAX_GATE_WAIT_MIN} min for the scheduled gate {state.scheduled_gate}",
            f"Change to a free gate if confirmed by {confirm_by}",
            f"Accept crew overtime (soft cost, {OVERTIME_MULTIPLIER}x) if it avoids a worse delay",
        ],
        "deadline": f"Gate change must be confirmed by {confirm_by} ({state.gate_change_notice_min} min before arrival)",
        "alternatives": icap["alternatives"]["ranked"],
        "icap": icap,
        "provenance": state.provenance,
    }
    assert_no_hindsight(facts)
    return facts


# The plan Ground assumes before anyone has negotiated: arrive at the disrupted time, scheduled gate.
# Args: state - world state.
# Returns: baseline Plan.
def baseline_plan(state: WorldState) -> Plan:
    return Plan(
        arrival_slot=min_to_hhmm(state.disrupted_arrival_min), ground_delay_min=0, holding_min=0,
        extra_fuel_min=0, gate=state.scheduled_gate, divert=False,
    )


class GroundAgent:
    # Args: client - AsyncAnthropic (or a compatible fake); model - model id; log_path - optional JSONL file
    #   that receives one line per LLM call.
    def __init__(self, client, model: str = DEFAULT_MODEL, log_path: Optional[Path] = None):
        self.client = client
        self.model = model
        self.log_path = Path(log_path) if log_path else None
        self.call_log: list[dict] = []
        self._role_prompt = PROMPT_PATH.read_text()

    # Round 1: parallel analysis. Ground proposes its preferred gate.
    # Args: state - world state.
    # Returns: AgentMessage with action "propose" (or "reject" if the model never gave valid output).
    async def propose(self, state: WorldState) -> AgentMessage:
        user = (
            "Round 1. Propose your preferred gate for the focal flight, "
            "using only the facts block. Action must be `propose`. Fill requested_next_action."
        )
        return await self._run(state, 1, user, "propose", baseline_plan(state), None, None)

    # Rounds 2-3: respond to the plan on the table.
    # Args: state - world state; round_no - 2 or 3; table_plan_id/table_plan - plan on the table;
    #   table_check - check_ground result for it; history - negotiation log entries so far (dicts).
    # Returns: AgentMessage with action accept/counter/reject.
    async def respond(
        self, state: WorldState, round_no: int, table_plan_id: str, table_plan: Plan,
        table_check: GroundCheck, history: list[dict],
    ) -> AgentMessage:
        cost = cost_ground(table_check)
        batna = build_icap(state)["alternatives"]["batna"]
        payload = {
            "round": round_no, "table_plan_id": table_plan_id,
            "table_plan": table_plan.model_dump(),
            "ground_check": table_check.to_dict(), "ground_cost": cost,
            "ready_time": min_to_hhmm(table_check.metrics["ready_time_min"]),
            # Table plan's Ground cost minus the cheapest valid Ground option at the disrupted arrival.
            "vs_batna_usd": None if batna is None else round(cost["total"] - batna["cost_usd"], 2),
            "log": history,
        }
        user = (
            f"Round {round_no}. Respond to the plan on the table: `accept`, `counter` or `reject`. "
            "Fill requested_next_action.\n" + json.dumps(payload, sort_keys=True)
        )
        return await self._run(state, round_no, user, "respond", table_plan, table_plan_id, table_check)

    # Calls the model, validates, re-asks once, and falls back to `reject`.
    # Args: see propose/respond; mode - "propose" or "respond"; base_plan - plan the decision edits.
    # Returns: AgentMessage.
    async def _run(self, state, round_no, user, mode, base_plan, table_id, table_check) -> AgentMessage:
        facts = build_ground_facts(state)
        system = [
            {"type": "text", "text": self._role_prompt},
            {"type": "text", "text": "FACTS:\n" + json.dumps(facts, sort_keys=True),
             "cache_control": {"type": "ephemeral"}},
        ]
        messages = [{"role": "user", "content": user}]
        for attempt in (1, 2):
            t0 = time.time()
            try:
                resp = await self.client.messages.parse(
                    model=self.model, max_tokens=MAX_TOKENS, system=system, messages=messages,
                    output_format=GroundDecision, output_config={"effort": EFFORT},
                )
            except ValidationError as e:
                self._log(round_no, attempt, None, t0, error=f"schema: {e.errors()[0]['msg']}")
                messages.append({"role": "user", "content": f"Your reply was invalid: {e.errors()[0]['msg']}. Reply again."})
                continue
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                self._log(round_no, attempt, None, t0, error=f"api: {type(e).__name__}")
                return self._reject(facts, round_no, "API error")
            self._log(round_no, attempt, resp, t0)
            if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
                return self._reject(facts, round_no, f"no usable output ({resp.stop_reason})")
            try:
                self._validate(resp.parsed_output, mode, [i["id"] for i in facts["icap"]["interests"]])
            except ValueError as e:
                messages.append({"role": "user", "content": f"Your reply was invalid: {e}. Reply again."})
                continue
            msg = self._to_message(resp.parsed_output, state, round_no, base_plan, table_id, table_check, facts)
            problems = validate_ranges(msg)
            if problems:
                messages.append({"role": "user", "content": f"Fix these problems and reply again: {problems}"})
                continue
            return msg
        return self._reject(facts, round_no, "invalid output twice")

    # Validates a decision against the protocol (code-side, not trusted to the model).
    # Args: d - model decision; mode - "propose" or "respond"; interest_ids - valid ICAP interest ids.
    # Raises: ValueError describing the problem.
    def _validate(self, d: GroundDecision, mode: str, interest_ids: list[str]) -> None:
        unknown = sorted(set(d.interests_cited) - set(interest_ids))
        if unknown:
            raise ValueError(f"unknown interest ids {unknown}; use only {interest_ids}")
        if d.action != "reject" and not d.interests_cited:
            raise ValueError("cite at least one interest id from the ICAP")
        if mode == "propose" and d.action != "propose":
            raise ValueError("round 1 action must be propose")
        if mode == "respond" and d.action not in ("accept", "counter", "reject"):
            raise ValueError("action must be accept, counter or reject")
        if d.action in ("propose", "counter") and not d.gate:
            raise ValueError("a gate is required")

    # Builds the full AgentMessage. Code fills every non-Ground plan field, the safety flags and the
    # ICAP brief; an accept of an off-table or Ground-invalid plan is overridden to reject.
    # Args: d - validated decision; base_plan - baseline (round 1) or table plan; table_id/table_check -
    #   the plan on the table and its Ground check (None in round 1); facts - this call's facts dict.
    # Returns: AgentMessage.
    def _to_message(self, d, state, round_no, base_plan, table_id, table_check, facts) -> AgentMessage:
        plan, plan_id = None, None
        if d.action == "accept":
            if d.plan_id != table_id:
                return self._override(facts, round_no, table_check, "accepted plan_id is not the plan on the table")
            if not table_check.valid:
                return self._override(facts, round_no, table_check, "the table plan fails the Ground check")
            plan, plan_id = base_plan, table_id
        elif d.action in ("propose", "counter"):
            plan = base_plan.model_copy(update={"gate": d.gate})
        flags = check_ground(plan, state).metrics["flags"] if plan is not None else []
        icap = self._icap(facts, d.requested_next_action, table_check if d.action in ("counter", "reject") else None,
                          d.interests_cited)
        return AgentMessage(
            **{"from": "ground"}, round=round_no, action=d.action, plan_id=plan_id, plan=plan,
            need=d.need, offer=d.offer, reason=d.reason, flags=flags, icap=icap,
        )

    # Builds the shared ICAPBrief from code facts (+ the model's requested next action).
    # Args: facts - facts dict; requested - model text; table_check - check of the plan being countered;
    #   cited - validated interest ids the decision relied on (shown after the interest text).
    # Returns: ICAPBrief.
    def _icap(self, facts: dict, requested: str, table_check: Optional[GroundCheck],
              cited: Optional[list[str]] = None) -> ICAPBrief:
        failed = None
        if table_check is not None and not table_check.valid:
            failed = FailedConstraint(
                rule="gate",
                evidence=[f"table_plan.ground_check.{v.rule_id}: {v.message}" for v in table_check.violations],
            )
        return ICAPBrief(
            interest=facts["interest"] + (f" [cites {', '.join(cited)}]" if cited else ""),
            failed_constraint=failed,
            alternatives=[Alternative(plan_ref=a["plan_ref"], summary=a["summary"], status="candidate")
                          for a in facts["alternatives"][:3]],
            concessions=facts["concessions"], deadline=facts["deadline"],
            requested_next_action=requested or "see need",
        )

    # Code override: turns an unacceptable accept into a reject that records why.
    # Args: facts, round_no, table_check - as above; why - short cause (<= 15 words).
    # Returns: reject AgentMessage.
    def _override(self, facts, round_no, table_check, why: str) -> AgentMessage:
        return AgentMessage(
            **{"from": "ground"}, round=round_no, action="reject",
            need="a table plan that passes the Ground check", offer="none",
            reason=f"Code override: {why}.", flags=[],
            icap=self._icap(facts, "Middleman: resend the current table plan", table_check),
        )

    # Deterministic stand-in when the model gives nothing usable (treated as reject per CLAUDE.md).
    # Args: facts - facts dict; why - short cause for the log.
    # Returns: reject AgentMessage.
    def _reject(self, facts: dict, round_no: int, why: str) -> AgentMessage:
        return AgentMessage(
            **{"from": "ground"}, round=round_no, action="reject", need="a valid Ground reply", offer="none",
            reason=f"Ground gave no valid response: {why}.", flags=[],
            icap=self._icap(facts, "Middleman: use the table plan or the fallback", None),
        )

    # Appends one LLM-call record to memory and, if configured, to the JSONL log.
    # Args: resp - API response or None; error - failure text if no response.
    def _log(self, round_no: int, attempt: int, resp, t0: float, error: Optional[str] = None) -> None:
        entry = {"ts": time.time(), "agent": "ground", "round": round_no, "attempt": attempt,
                 "model": self.model, "latency_s": round(time.time() - t0, 2), "error": error}
        if resp is not None:
            u = resp.usage
            entry.update(
                request_id=getattr(resp, "_request_id", None), stop_reason=resp.stop_reason,
                usage={
                    "input": u.input_tokens, "output": u.output_tokens,
                    "cache_creation": getattr(u, "cache_creation_input_tokens", None),
                    "cache_read": getattr(u, "cache_read_input_tokens", None),
                },
            )
        self.call_log.append(entry)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
