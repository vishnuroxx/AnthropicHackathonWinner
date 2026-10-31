"""Ground Ops agent: separate system prompt, one call per round, only Ground's facts.

The model decides only gate + turnaround (GroundDecision). Code assembles the full Plan, so
Ground cannot touch ATC/Pilot fields. Invalid output is re-asked once, then becomes `reject`.
"""
import json
import time
from pathlib import Path
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, ValidationError, field_validator

from checker_ground import GroundCheck
from cost_ground import cost_ground
from limits import GATE_CHANGE_NOTICE_MIN, MAX_GATE_WAIT_MIN, OVERTIME_MULTIPLIER
from schema import AgentMessage, Plan, min_to_hhmm
from world_fixture import WorldState, walk_min

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 4000
EFFORT = "medium"
PROMPT_PATH = Path(__file__).parent / "prompts" / "ground.md"
ALLOWED_FLAGS = {"CREW_OVERTIME", "CONNECTION_RISK", "GATE_SHORTAGE"}
# Outcome columns agents must never see (CLAUDE.md section 6, "No hindsight").
FORBIDDEN_FIELDS = {
    "departure_time", "arrival_time", "arrival_delay", "departure_delay",
    "wheels_on", "wheels_off", "elapsed_time", "air_time", "taxi_in", "taxi_out",
}


class GroundDecision(BaseModel):
    """What the model returns: only Ground's levers plus the short text fields."""
    action: Literal["propose", "accept", "counter", "reject"]
    plan_id: Optional[str] = None
    gate: str
    turnaround_min: int
    need: str
    offer: str
    reason: str
    flags: list[str]

    # Word limits from the message contract (need/offer 20, reason 30).
    # Args: v - text; info - pydantic field info.
    # Returns: v unchanged.
    # Raises: ValueError if over the limit.
    @field_validator("need", "offer", "reason")
    @classmethod
    def _word_limit(cls, v: str, info) -> str:
        limit = 30 if info.field_name == "reason" else 20
        if len(v.split()) > limit:
            raise ValueError(f"{info.field_name} exceeds {limit} words")
        return v


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
    horizon_end = state.disrupted_arrival_min + 240
    free_gates = [
        {"gate": g, "terminal": g[0], "walk_min_from_scheduled_gate": walk_min(state.scheduled_gate, g)}
        for g, w in state.gate_busy.items()
        if g != state.scheduled_gate and not any(x.start < horizon_end and x.end > state.now_min for x in w)
    ]
    facts = {
        "airport": state.airport,
        "limits": {
            "gates": state.limits.gates, "min_turnaround_min": state.limits.min_turnaround_min,
            "spare_gates_at_any_time": state.limits.spare_gates, "source": state.limits.source,
        },
        "rules": {
            "gate_change_notice_min": GATE_CHANGE_NOTICE_MIN, "max_gate_wait_min": MAX_GATE_WAIT_MIN,
            "crew_overtime_multiplier": OVERTIME_MULTIPLIER,
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

    # Round 1: parallel analysis. Ground proposes its preferred gate and turnaround.
    # Args: state - world state.
    # Returns: AgentMessage with action "propose" (or "reject" if the model never gave valid output).
    async def propose(self, state: WorldState) -> AgentMessage:
        user = (
            "Round 1. Propose your preferred gate and turnaround for the focal flight, "
            "using only the facts block. Action must be `propose`."
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
        payload = {
            "round": round_no, "table_plan_id": table_plan_id,
            "table_plan": table_plan.model_dump(),
            "ground_check": table_check.to_dict(), "ground_cost": cost_ground(table_check),
            "log": history,
        }
        user = (
            f"Round {round_no}. Respond to the plan on the table: `accept`, `counter` or `reject`.\n"
            + json.dumps(payload, sort_keys=True)
        )
        return await self._run(state, round_no, user, "respond", table_plan, table_plan_id, table_check)

    # Calls the model, validates, re-asks once, and falls back to `reject`.
    # Args: see propose/respond; mode - "propose" or "respond"; base_plan - plan the decision edits.
    # Returns: AgentMessage.
    async def _run(self, state, round_no, user, mode, base_plan, table_id, table_check) -> AgentMessage:
        system = [
            {"type": "text", "text": self._role_prompt},
            {"type": "text", "text": "FACTS:\n" + json.dumps(build_ground_facts(state), sort_keys=True),
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
                return self._reject(state, round_no, "API error")
            self._log(round_no, attempt, resp, t0)
            if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
                return self._reject(state, round_no, f"no usable output ({resp.stop_reason})")
            try:
                self._validate(resp.parsed_output, mode, table_id, table_check)
            except ValueError as e:
                messages.append({"role": "user", "content": f"Your reply was invalid: {e}. Reply again."})
                continue
            return self._to_message(resp.parsed_output, round_no, base_plan, table_id)
        return self._reject(state, round_no, "invalid output twice")

    # Validates a decision against the protocol (code-side, not trusted to the model).
    # Raises: ValueError describing the problem.
    def _validate(self, d: GroundDecision, mode: str, table_id, table_check) -> None:
        if mode == "propose" and d.action != "propose":
            raise ValueError("round 1 action must be propose")
        if mode == "respond" and d.action not in ("accept", "counter", "reject"):
            raise ValueError("action must be accept, counter or reject")
        if d.action == "accept":
            if d.plan_id != table_id:
                raise ValueError(f"accept must carry plan_id {table_id}")
            if not table_check.valid:
                raise ValueError("cannot accept a plan whose Ground check is invalid")
        if d.action in ("propose", "counter") and (not d.gate or d.turnaround_min <= 0):
            raise ValueError("gate and a positive turnaround_min are required")
        bad = set(d.flags) - ALLOWED_FLAGS
        if bad:
            raise ValueError(f"unknown flags {sorted(bad)}")

    # Builds the full AgentMessage: code fills every non-Ground plan field.
    # Args: d - validated decision; base_plan - baseline (round 1) or table plan.
    # Returns: AgentMessage.
    def _to_message(self, d: GroundDecision, round_no: int, base_plan: Plan, table_id) -> AgentMessage:
        plan, plan_id = None, None
        if d.action == "accept":
            plan, plan_id = base_plan, table_id
        elif d.action in ("propose", "counter"):
            plan = base_plan.model_copy(update={"gate": d.gate, "turnaround_min": d.turnaround_min})
        return AgentMessage(
            **{"from": "ground"}, round=round_no, action=d.action, plan_id=plan_id, plan=plan,
            need=d.need, offer=d.offer, reason=d.reason, flags=d.flags,
        )

    # Deterministic stand-in when the model gives nothing usable (treated as reject per CLAUDE.md).
    # Args: why - short cause for the log (<= 30 words).
    # Returns: reject AgentMessage.
    def _reject(self, state: WorldState, round_no: int, why: str) -> AgentMessage:
        return AgentMessage(
            **{"from": "ground"}, round=round_no, action="reject",
            reason=f"Ground gave no valid response: {why}.", flags=[],
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
