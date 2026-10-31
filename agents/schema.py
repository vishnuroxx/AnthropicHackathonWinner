"""Shared agent message schema (CLAUDE.md section 7). Every agent's output must validate against AgentMessage.

Owned jointly by the agent lanes and the middleman lane: change it only with the team.
Ranges (minutes >= 0, HH:MM format, word limits) are enforced in Python by `validate_ranges`,
because structured outputs do not support min/max constraints in the schema.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AgentName = Literal["atc", "pilot", "ground"]
Action = Literal["propose", "accept", "counter", "reject"]
Flag = Literal["MINIMUM_FUEL", "DUTY_LIMIT", "DIVERT_RECOMMENDED", "CANCEL_RECOMMENDED"]


class Plan(BaseModel):
    arrival_slot: str = Field(description="Arrival time at the destination, local HH:MM")
    ground_delay_min: int = Field(description="Minutes the take-off is delayed at the origin")
    holding_min: int = Field(description="Minutes of airborne holding before landing")
    extra_fuel_min: int = Field(description="Extra holding fuel loaded before departure, in minutes")
    gate: str = Field(description="Arrival gate id, e.g. C14")
    divert: bool = Field(description="True only if the flight diverts to its alternate airport")


class FailedConstraint(BaseModel):
    rule: Literal["fuel", "crew_duty", "gate", "slot", "none"]
    evidence: list[str] = Field(description="Fact keys with values, e.g. 'plans.P2.assessment.fuel_margin_min=-7.1'")


class Alternative(BaseModel):
    plan_ref: str = Field(description="Candidate id, e.g. P2 or P1-ground-delay")
    summary: str
    status: Literal["candidate", "confirmed"] = Field(description="candidate until the owning agent confirms it")


class ICAPBrief(BaseModel):
    """Optional decision brief (Interests, Constraints, Alternatives, Priorities). Additive: agents and the
    middleman may ignore it; the consensus log and decision document show it."""
    interest: str = Field(description="The outcome being protected and why (interest, not position)")
    failed_constraint: Optional[FailedConstraint] = None
    alternatives: list[Alternative] = Field(default_factory=list, description="Ranked, best first")
    concessions: list[str] = Field(default_factory=list, description="What this agent can give up")
    deadline: Optional[str] = None
    requested_next_action: str


class AgentMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: AgentName = Field(alias="from")
    round: int
    action: Action
    plan_id: Optional[str] = Field(default=None, description="Id of the table plan when accepting, e.g. P3")
    plan: Optional[Plan] = Field(default=None, description="Required for propose and counter")
    need: str = Field(description="What this agent needs, <= 20 words")
    offer: str = Field(description="What this agent can give, <= 20 words")
    reason: str = Field(description="<= 30 words, cites a fact key, constraint or objective")
    flags: list[Flag] = Field(default_factory=list)
    icap: Optional[ICAPBrief] = Field(default=None, description="Optional ICAP decision brief")


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_ranges(msg: AgentMessage) -> list[str]:
    """Return a list of problems the JSON schema cannot express. Empty list = OK."""
    problems = []
    if msg.action in ("propose", "counter") and msg.plan is None:
        problems.append(f"action '{msg.action}' requires a plan")
    if msg.action == "accept" and not msg.plan_id:
        problems.append("action 'accept' requires plan_id")
    if msg.plan is not None:
        p = msg.plan
        if not _HHMM.match(p.arrival_slot):
            problems.append(f"arrival_slot '{p.arrival_slot}' is not HH:MM")
        for name in ("ground_delay_min", "holding_min", "extra_fuel_min"):
            if getattr(p, name) < 0:
                problems.append(f"{name} must be >= 0")
    for name, limit in (("need", 20), ("offer", 20), ("reason", 30)):
        if len(getattr(msg, name).split()) > limit + 5:  # small tolerance; trimmed by the UI
            problems.append(f"{name} longer than {limit} words")
    return problems
