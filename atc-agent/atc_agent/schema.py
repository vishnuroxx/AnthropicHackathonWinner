"""Validate an ATC message against agent contract v0.2, CLAUDE.md §7 and the ATC spec (CAP-4, 6, 7, 8, 10, 11)."""
import re

from . import config
from .menu import Option

NUM = re.compile(r"\d{1,2}:\d{2}|\d+(?:\.\d+)?")
LIMITS = {"need": 20, "offer": 20, "reason": 30}
MARGIN_WORDS = ("margin", "thin", "spare", "capacity", "cap")
ACTIONS = {1: {"propose"}, 2: {"accept", "counter", "reject"}, 3: {"accept", "reject"}}
PLAN_KEYS = ("arrival_slot", "ground_delay_min", "holding_min", "extra_fuel_min")


def numbers_in(text: str) -> set[str]:
    return set(NUM.findall(text or ""))


def validate(msg: dict, round_no: int, menu: list[Option], allowed_text: str, flags: set[str],
             table: dict | None = None) -> list[str]:
    """table = table-plan dict {plan_id, proposed_by, source_id, plan, check, cost_usd, total_system_delay_min}."""
    errs: list[str] = []
    if not isinstance(msg, dict):
        return ["reply is not a JSON object"]
    if msg.get("from") != "atc":
        errs.append('"from" must be "atc"')
    if msg.get("round") != round_no:
        errs.append(f'"round" must be {round_no}')
    action = msg.get("action")
    allowed = ACTIONS.get(round_no, set())
    if action not in allowed:
        errs.append(f'"action" must be one of {sorted(allowed)} in round {round_no}')
    msg_flags = msg.get("flags") or []
    if not isinstance(msg_flags, list) or any(f not in config.FLAGS for f in msg_flags):
        errs.append(f"flags may only contain {list(config.FLAGS)}")

    by_id = {o.option_id: o for o in menu}
    raw_plan = msg.get("plan")
    if raw_plan is not None and not isinstance(raw_plan, dict):
        errs.append('"plan" must be an object or null')
        raw_plan = None
    plan = raw_plan or {}
    table_plan = (table or {}).get("plan") or {}
    table_opt = next((o for o in menu if (o.arrival_slot, o.ground_delay_min, o.holding_min) ==
                      (table_plan.get("arrival_slot"), table_plan.get("ground_delay_min"),
                       table_plan.get("holding_min"))), None) if table else None

    opt: Option | None = None  # the option the fuel and margin rules apply to
    if action in ("propose", "counter"):
        opt = by_id.get(msg.get("plan_id"))
        if opt is None:
            errs.append(f'"plan_id" {msg.get("plan_id")!r} is not an option_id in option_menu')
        else:
            for k in PLAN_KEYS:
                if plan.get(k) != getattr(opt, k):
                    errs.append(f"plan.{k} must equal option {opt.option_id}'s value {getattr(opt, k)!r}")
            if not opt.valid:
                errs.append(f"option {opt.option_id} is invalid")
    elif action == "accept":
        if not table:
            errs.append('"accept" needs a table plan')
        else:
            if msg.get("plan_id") != table.get("plan_id"):
                errs.append(f'"accept" must use the table plan_id {table.get("plan_id")}')
            for k in PLAN_KEYS:
                if plan.get(k) != table_plan.get(k):
                    errs.append(f"plan.{k} must equal table plan's value {table_plan.get(k)!r}")
            opt = table_opt
    elif action == "reject":
        if not str(msg.get("reason") or "").strip():
            errs.append('"reject" needs a non-empty reason')
    if plan.get("gate") is not None or plan.get("divert") not in (False, None):
        errs.append("ATC must not set gate or divert")

    if action == "counter":
        if not table:
            errs.append('"counter" needs a table plan')
        elif opt and table_opt:
            if opt.option_id == table_opt.option_id:
                errs.append('"counter" must name a different option')
            elif ("EMERGENCY_FUEL" not in flags and opt.total_system_delay_min
                  > table_opt.total_system_delay_min - config.CAP10_TOLERANCE_MIN):
                errs.append(f"CAP-10: counter only if total_system_delay_min is at least "
                            f"{config.CAP10_TOLERANCE_MIN} lower than the table's ({table_opt.total_system_delay_min}); "
                            f"otherwise accept")

    for field, limit in LIMITS.items():
        words = len(str(msg.get(field, "")).split())
        if words > limit:
            errs.append(f'"{field}" has {words} words; max {limit}')
    invented = numbers_in(" ".join(str(msg.get(f, "")) for f in LIMITS)) - numbers_in(allowed_text)
    if invented:
        errs.append(f"CAP-6: numbers not in your facts or menu: {sorted(invented)}")

    if opt:
        if "EMERGENCY_FUEL" in flags:
            earliest = min((o.arrival_slot for o in menu if o.valid))
            if opt.arrival_slot != earliest:
                errs.append(f"CAP-8: EMERGENCY_FUEL needs the earliest valid slot {earliest}")
        elif "MINIMUM_FUEL" in flags:
            if opt.holding_min > 0:
                errs.append("CAP-8: MINIMUM_FUEL forbids added holding")
            if table_plan.get("arrival_slot") and opt.arrival_slot > table_plan["arrival_slot"]:
                errs.append("CAP-8: MINIMUM_FUEL forbids a later slot than the table plan")
        if opt.spare_slots_in_hour <= 0:
            said = (str(msg.get("need", "")) + " " + str(msg.get("reason", ""))).lower()
            if not any(w in said for w in MARGIN_WORDS):
                errs.append("CAP-11: option leaves no spare arrival slot; name the thin margin in need or reason")
    return errs
