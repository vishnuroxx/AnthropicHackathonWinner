"""ATC agent: one Claude call per round, schema-validated, one re-ask, then reject (CLAUDE.md §5)."""
import hashlib
import json
import os
import time
from pathlib import Path

from . import config
from .facts import build_atc_facts
from .menu import Option, build_menu, cheapest_valid, earliest_valid
from .prompt import SYSTEM, user_message
from .schema import validate
from .world_stub import World

ENVELOPE_KEYS = frozenset({"schema_version", "negotiation_id", "message_id", "state_revision", "ruleset_id",
                           "status", "validator_errors"})
ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
CACHE_DIR = ROOT / ".cache"


def load_env() -> None:
    """Read ANTHROPIC_API_KEY from the nearest .env.local (worktree root or main checkout). No extra package."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    for d in [config.REPO, *config.REPO.parents]:
        f = d / ".env.local"
        if f.is_file():
            for line in f.read_text().splitlines():
                k, _, v = line.partition("=")
                if k.strip() and v.strip() and not k.lstrip().startswith("#"):
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


def parse_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


class ATCAgent:
    def __init__(self, world: World, dry_run: bool = False, negotiation_id: str | None = None):
        self.world = world
        f = world.focal
        self.negotiation_id = negotiation_id or             f'{world.dest}-{world.date.replace("-", "")}-{f["AIRLINE"]}{f["FLIGHT_NUMBER"]}'
        self.menu: list[Option] = build_menu(world)
        self.flags: set[str] = set()
        self.dry_run = dry_run
        self.client = None
        if not dry_run:
            import anthropic
            load_env()
            self.client = anthropic.Anthropic()
        LOG_DIR.mkdir(exist_ok=True)
        self.log_path = LOG_DIR / f"atc-calls-{time.strftime('%Y%m%d')}.jsonl"

    # --- public API for the middle man ---
    def propose(self) -> dict:
        return self._turn(1)

    def respond(self, round_no: int, table: dict, check: dict, others: list[dict]) -> dict:
        for m in others:
            self.flags |= {f for f in m.get("flags", []) if f in config.FLAGS}
        return self._turn(round_no, table, check, others)

    # --- internals ---
    def _envelope(self, round_no: int) -> dict:
        """Code-filled envelope fields; never taken from the LLM."""
        return {"schema_version": config.SCHEMA_VERSION, "negotiation_id": self.negotiation_id,
                "message_id": f"{self.negotiation_id}-r{round_no}-atc", "state_revision": 0,
                "ruleset_id": config.RULESET_ID}

    def _turn(self, round_no: int, table: dict | None = None, check: dict | None = None,
              others: list[dict] | None = None) -> dict:
        facts = build_atc_facts(self.world, self.menu, self.flags)
        user = user_message(round_no, facts, table, check, others)
        allowed_text = user
        messages = [{"role": "user", "content": user}]
        errors: list[str] = []
        for attempt in (1, 2):
            text = self._stand_in(round_no, table) if self.dry_run else self._call(messages)
            body = parse_json(text)
            if body is not None:
                body = {k: v for k, v in body.items() if k not in ENVELOPE_KEYS}
            errors = validate(body, round_no, self.menu, allowed_text, self.flags, table)                 if body is not None else ["no JSON object"]
            self._log(round_no, attempt, text, errors)
            if not errors:
                return {**self._envelope(round_no), **body, "status": "OK", "validator_errors": []}
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": user_message(round_no, facts, table, check, others, errors)}]
        return {**self._envelope(round_no), "from": "atc", "round": round_no, "action": "reject",
                "plan_id": None, "plan": None, "need": "", "offer": "",
                "reason": "Invalid output after one re-ask; treated as reject.", "flags": [],
                "status": "ERROR", "validator_errors": errors}

    def _call(self, messages: list[dict]) -> str:
        key = hashlib.sha256(json.dumps([config.MODEL, SYSTEM, messages]).encode()).hexdigest()[:24]
        cached = CACHE_DIR / f"{key}.txt"
        if cached.is_file():  # re-runs are free and reproducible (CLAUDE.md §13)
            return cached.read_text(encoding="utf-8")
        t0 = time.time()
        resp = self.client.messages.create(
            model=config.MODEL, max_tokens=config.MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=messages)
        text = "".join(b.text for b in resp.content if b.type == "text")
        self._last_meta = {"latency_s": round(time.time() - t0, 2), "usage": resp.usage.model_dump()}
        CACHE_DIR.mkdir(exist_ok=True)
        cached.write_text(text, encoding="utf-8")
        return text

    def _stand_in(self, round_no: int, table: dict | None) -> str:
        """Dry run: deterministic reply with no LLM, to exercise the pipeline. Never used in the demo path."""
        if "EMERGENCY_FUEL" in self.flags:
            opt = earliest_valid(self.menu)
        elif "MINIMUM_FUEL" in self.flags:
            opt = min((o for o in self.menu if o.valid and o.holding_min == 0), key=lambda o: o.arrival_slot)
        else:
            opt = cheapest_valid(self.menu)
        body = {"from": "atc", "round": round_no, "need": "Thin margin: no spare arrival slot this hour.", "flags": []}
        if round_no == 1:
            body |= {"action": "propose", "plan_id": opt.option_id, "plan": opt.plan()}
        else:
            tp = table["plan"]
            t_opt = next((o for o in self.menu if (o.arrival_slot, o.ground_delay_min, o.holding_min) ==
                          (tp["arrival_slot"], tp["ground_delay_min"], tp["holding_min"])), opt)
            wants_counter = opt.option_id != t_opt.option_id and (
                "EMERGENCY_FUEL" in self.flags
                or opt.total_system_delay_min <= t_opt.total_system_delay_min - config.CAP10_TOLERANCE_MIN)
            if wants_counter and round_no == 2:
                body |= {"action": "counter", "plan_id": opt.option_id, "plan": opt.plan()}
            elif wants_counter:
                body |= {"action": "reject", "plan_id": None, "plan": None}
            else:
                opt = t_opt
                body |= {"action": "accept", "plan_id": table["plan_id"], "plan": dict(tp)}
        if body["action"] == "reject":
            body |= {"offer": "", "reason": f"Own option {opt.option_id} has lower total_system_delay_min "
                                            f"({opt.total_system_delay_min}) than the table; no counter in round {round_no}."}
        else:
            body |= {"offer": f"Slot {opt.arrival_slot} via ground delay.",
                     "reason": f"Arrival cap reached; knock-on {opt.knock_on_min} min."}
        return json.dumps(body)

    def _log(self, round_no: int, attempt: int, text: str, errors: list[str]) -> None:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": "atc", "round": round_no, "attempt": attempt,
                 "negotiation_id": self.negotiation_id, "message_id": f"{self.negotiation_id}-r{round_no}-atc",
                 "dry_run": self.dry_run, "model": config.MODEL, "raw": text, "validator_errors": errors,
                 **getattr(self, "_last_meta", {})}
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
