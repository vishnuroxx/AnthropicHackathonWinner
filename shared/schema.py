"""Shared agent message contract, per CLAUDE.md section 7.

`Plan.turnaround_min` is an addition to the section-7 schema: the Ground lever
"shorter turnaround if crew allow" needs a field to be expressed. None means the
airport minimum. Flag to the team before relying on it elsewhere.
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLOT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# Converts "HH:MM" or DOT-style "HHMM" (incl. "2400") to minutes from midnight.
# Args: s - time string.
# Returns: minutes from midnight (0..1440).
# Raises: ValueError if s is not a valid time.
def hhmm_to_min(s: str) -> int:
    s = s.strip().replace(":", "")
    if not s.isdigit() or len(s) > 4:
        raise ValueError(f"bad time {s!r}")
    s = s.zfill(4)
    h, m = int(s[:2]), int(s[2:])
    if m > 59 or h > 24:
        raise ValueError(f"bad time {s!r}")
    return h * 60 + m


# Formats minutes from midnight as "HH:MM", wrapping past midnight.
# Args: m - minutes from midnight (may exceed 1440).
# Returns: "HH:MM" string.
def min_to_hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


# Counts whitespace-separated words in a string.
# Args: text - the string.
# Returns: word count.
def _words(text: str) -> int:
    return len(text.split())


class Plan(BaseModel):
    arrival_slot: str
    ground_delay_min: int
    holding_min: int
    extra_fuel_min: int
    gate: str
    divert: bool
    turnaround_min: Optional[int] = None

    # Checks arrival_slot is a valid "HH:MM" string.
    # Args: v - candidate value.
    # Returns: v unchanged.
    # Raises: ValueError if the format is wrong.
    @field_validator("arrival_slot")
    @classmethod
    def _slot_format(cls, v: str) -> str:
        if not _SLOT_RE.match(v):
            raise ValueError("arrival_slot must be HH:MM")
        return v


class AgentMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: Literal["atc", "pilot", "ground"] = Field(alias="from")
    round: int
    action: Literal["propose", "accept", "counter", "reject"]
    plan_id: Optional[str] = None
    plan: Optional[Plan] = None
    need: str = ""
    offer: str = ""
    reason: str = ""
    flags: list[str] = []

    # Enforces the contract word limits: need/offer <= 20, reason <= 30.
    # Args: v - candidate text; info - pydantic field info.
    # Returns: v unchanged.
    # Raises: ValueError if over the limit.
    @field_validator("need", "offer", "reason")
    @classmethod
    def _word_limit(cls, v: str, info) -> str:
        limit = 30 if info.field_name == "reason" else 20
        if _words(v) > limit:
            raise ValueError(f"{info.field_name} exceeds {limit} words")
        return v

    # Enforces rounds 1-3 only (hard turn cap).
    # Args: v - round number.
    # Returns: v unchanged.
    # Raises: ValueError if outside 1..3.
    @field_validator("round")
    @classmethod
    def _round_range(cls, v: int) -> int:
        if not 1 <= v <= 3:
            raise ValueError("round must be 1..3")
        return v
