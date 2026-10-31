# ATC consensus-log proposal

For: Ryan (ATC lane). Status: proposal, 14:50 Sat 31 Oct. Nothing in it is built yet.
Source: `Traceable_Consensus_Logging_Plan.md` (Downloads), which was written against contract v0.1.
Target: contract v0.2 hybrid (`_bmad-output/specs/spec-agent-contract/`) and `CLAUDE.md` §5, §11–13.

**Already settled by Ryan (not reopened here):** (a) check status has three states: INVALID when a hard rule FAILs, ERROR when a hard rule is UNKNOWN or the checker errors, VALID otherwise. (b) Separation checks report seconds (`"s"`). (c) Violation strings start with the rule id; `proposed_by: "fallback"` only when no agent plan is valid; `plan` is null on reject. (d) C-CAP-1 compares arrivals in the landing hour with the hourly cap of 45, 31 or 37, in unit `arrivals_per_hour`. (f) Moving the contract into the framing doc is deferred.
Another worker is editing `menu.py` `check_slot` and the contract files right now. This plan leaves both alone.

## 1. Goal and scope

Goal: any ATC line in the consensus log can be traced back to four things, all readable without an LLM:
- exactly what ATC was shown;
- every raw model output, attempt by attempt;
- why the validator accepted or refused each attempt;
- which code-computed numbers support the message.

| Concern | Owner | Why |
|---|---|---|
| Consensus log: one 10-field line per agent message (contract §4) | Team A (middleman) | `CLAUDE.md` §11, CAP-8. Only the middleman sees all three agents |
| Outcome line (consensus, halt or cancel) and the human Approve/Reject line | Team A writes; UI (C) triggers the human line | Only the middleman decides when to stop (§5) |
| Checks, cost, fallback search evidence | Team B | Non-goals of contract v0.2 |
| ATC trace: delivered input, raw outputs, validator result, effective message, menu, ATC manifest, ATC turn summary | **ATC (Ryan)** | Only ATC sees its own prompt and raw output |
| Reference helpers that build and check log lines | **ATC**, offered to A, C and D | They cost little, and they keep every lane on one shape |

How the two records join: on `message_id` (`{negotiation_id}-r{round}-atc`), which code already builds. No new contract field is needed.

Assumptions this proposal makes (each needs a quick check):
1. Team A calls `ATCAgent` in-process (a Python import). Over HTTP, `trace_for()` is not reachable, so team A would read the run folder instead.
2. Team A builds `negotiation_id` with the same formula.
3. `atc-agent/runs/` is writable and gitignored like `logs/` and `.cache/`.
4. Commit `46b00a9` on origin/main ("shared message schema", from the Pilot lane) has not been inspected. If it differs from v0.2, the helpers in §4 follow whichever schema the team adopts.

## 2. Reconciling the logging plan with contract v0.2

| Logging-plan element | Verdict | Why |
|---|---|---|
| Three levels of detail (summary, decision trail, evidence) built from one record | Adopt | Serves the trust and traceability criterion (20%). ATC renders its own turns; the document crafter (§12) renders the full story |
| One coordinator-owned logging service | Adapt | Team A owns the consensus log; ATC writes only its own trace, keyed by `message_id` |
| SQLite as the authoritative store | Drop | See §3.1. The contract says JSONL, and there are 30 min left |
| JSONL, artifacts folder, manifest, `summary.md` export | Adopt (ATC slice) | Matches CAP-8 and §11; needs no new dependency |
| Session manifest written before turn 1 | Adapt | ATC writes its own part only (§3.5). Ruleset parsing belongs to team B |
| Exact input delivered to each agent | Adopt | Not stored anywhere today: the cache keeps outputs only. **This is the biggest gap** |
| `negotiation_id`, `message_id`, `ruleset_id`, `state_revision` | Adopt as in v0.2 | Already in the envelope |
| `event_id`, `sequence` | Adapt | ATC-local: event id `{message_id}-a{attempt}-{type}`, plus a counter per run. Global ordering is team A's |
| `plan_id` plus `plan_hash` | Adapt | P# stays the id (CAP-4). On an accept, the ATC trace stores the sha256 of the table plan's `plan`, so the accept is tied to the plan's content. The contract does not change |
| `parent_plan_ids` plus a machine diff | Adapt | On a counter, the ATC trace stores `counter_of: P#` and the changed fields. This feeds the "what changed" sentences |
| `check_id`, `artifact_id` | Adapt | Artifacts are named by content hash. No separate check id: `message_id` plus the plan hash identifies a check |
| UTC times; `simulation_time_s` | Adapt / drop | The contract `ts` stays local; the ATC trace adds `ts_utc`. v0.2 rejected seconds in plan fields |
| Event types SESSION_STARTED, AGENT_OUTPUT_RECEIVED, MESSAGE_INVALID, AGENT_MESSAGE | Adopt as ATC events | See §3.2 |
| CANDIDATE_REGISTERED, TURN_*, CONSENSUS_*, FALLBACK_STARTED, FINAL_RESULT | Hand to team A | These belong to the middleman. Outcome options are in §7(e). Acceptance-set intersection and the shared catalogue are v0.2 non-goals |
| STATE_CHANGED, SELECTION_INVALIDATED, RECOVERY_RESUMED | Drop | `state_revision` is 0; the world is static |
| Keep the original output separate from the validated message | Adopt | Half done already (`raw` per attempt). Add the effective message and the link between them |
| Check fields `rule_id`, `result`, `actual`, `limit`, `unit` | Adopt as in v0.2 | Already in the contract |
| Per-check `operator`, `severity`, `input_refs`, `rule_source_ref`, `reason_code`, `explanation` | Defer | Severity and source already sit in the rule registry. Adding them would change team B's shape |
| `NOT_APPLICABLE` result | Drop | Settled (a). Out-of-scope rules are listed as "not evaluated" in the manifest |
| Coverage check | Adapt | The ATC trace records expected vs present ATC-domain rule ids. A missing id is logged, not hidden. Enforcing it is team A's or B's job |
| `ConsensusEvidence` record | Drop | v0.2 consensus means all three accept one table P#. The outcome line lists the three accepting message ids |
| Fallback detail (trigger, search bounds, candidates) | Hand to A and B | At minimum: a trigger code and the search size in the outcome line (§7(e)) |
| Uniqueness invariants, atomic writes | Adapt (later) | ATC returns its stored message if called twice in one round |
| Crash recovery | Drop | The response cache makes a re-run free and identical for cached calls |
| Audit replay without an LLM | Adapt (later) | ATC replay re-validates the stored raw outputs against the stored inputs |
| Hash chain, tamper evidence | Drop | State the real limit instead (§8) |
| §7 fuel example ("45 min includes the 30 min reserve") | **Reject the assumption** | It conflicts with Ryan's accounting: the 45 min spare sits on top of the 30 min reserve. Under ours, 20 min of holding passes C-FUEL-1 (limit 45 + extra fuel) |
| §12 example timeline (Pilot rejects 20 min of holding) | Don't reuse in the pitch | It depends on the rejected fuel assumption |
| Readable text from deterministic templates | Adopt | No LLM in the summary |

## 3. Design

### 3.1 Storage
- **Option A: JSONL plus an artifacts folder per run** (`atc-agent/runs/{negotiation_id}/{run_id}/`).
  - Pros: no new dependency. Same format as CAP-8 and today's per-call log. The UI and eval read it with `json`. The run folder is the export, and it diffs cleanly.
  - Cons: no transactions or unique constraints. A crash can leave a half-written last line, so readers must skip a bad final line. Invariants are enforced in code only.
- **Option B: SQLite (`sqlite3`, standard library) as the authoritative store, with a JSONL export.**
  - Pros: transactions, a unique (negotiation, round, agent) slot, and one query for the UI.
  - Cons: the authoritative consensus store would be team A's, not ATC's. Two formats to keep in sync. The schema work won't fit in 30 min, and the contract already says JSONL.
- **Recommendation: A.** Keep `logs/atc-calls-YYYYMMDD.jsonl` as the cross-run debug log; the run folder is the evidence.

Run folder contents: `manifest.json`, `events.jsonl`, `artifacts/`, `summary.md`.

### 3.2 Events the ATC emits
Every event carries: `event_id, seq, type, ts, ts_utc, negotiation_id, message_id, round, attempt, artifact_refs[], caused_by, payload`.

| type | When | Payload |
|---|---|---|
| `ATC_RUN_STARTED` | `ATCAgent` is created | manifest ref, menu ref, menu size, count of valid options |
| `ATC_INPUT_DELIVERED` | before each attempt | ref to the exact user-message text, `prompt_version`, `table` (full dict) and its `table_plan_hash`, `flags` (sorted), the other agents' message ids, re-ask errors shown |
| `ATC_OUTPUT_RECEIVED` | after each attempt | raw text verbatim, `parse_ok`, `discarded_keys` (envelope keys the LLM emitted), `cache_hit`, `dry_run`, `model`, `latency_s`, `usage` (both null on a cache hit) |
| `ATC_MESSAGE_INVALID` | an attempt fails validation | `validator_errors`, `next`: `"re-ask"` or `"error-reject"` |
| `ATC_MESSAGE_EMITTED` | the message is returned to the middleman | effective enveloped message, `source_attempt`, `original_output_ref`, `plan_hash`, `counter_of` and `plan_diff` (counters only), ATC's stub `check_slot` result, `coverage {expected, present, missing}` |

`caused_by` links each re-ask to the failed attempt before it. Later: `ATC_DUPLICATE_CALL`.

### 3.3 Original output vs validated message
- Every raw attempt is kept verbatim and never edited. The effective message points to the attempt it came from.
- If the model said "accept" and failed validation twice, the trace shows both raw accepts and the effective `reject` with status ERROR. Code never manufactures an acceptance; `agent.py:96` already guarantees that.
- Envelope keys the LLM wrote are dropped today without a trace (`agent.py:89`). Record them as `discarded_keys` so the drop is visible.
- No secrets: the key never enters a message; the trace holds only the prompt and the output.

### 3.4 Delivered-input artifacts
- `system-{prompt_version}.txt`, written once per run. `prompt_version` is `sha256(SYSTEM)[:12]`.
- Per attempt, the exact user-message string: facts, table, checker result, other agents' messages and re-ask errors. Files are named by content, so identical inputs are stored once.
- `menu-{hash}.json`: the full `asdict` of every Option, including `violations`. The facts use `as_dicts`, which drops them.
- **Hard rule for the worker:** don't change what is sent to the model. The cache key is `sha256(model, SYSTEM, messages)`, so any change to the prompt or the facts misses the cache and forces new live calls.

### 3.5 ATC manifest
- **Ids, code and model:** `negotiation_id`, `run_id` (local timestamp), `schema_version`, `ruleset_id`, `state_revision: 0`, git short commit (`"unknown"` if git fails), `model`, `max_tokens`, `dry_run`, `prompt_version`.
- **Sources:** workbook path and sha256 (the file is small); `flights.csv` path, size and mtime. The CSV is **not hashed**: at several hundred MB that is too slow. Say so.
- **World snapshot:** `date, dest, focal` (already stripped of hindsight columns), `event, focal_earliest_arr_min, weather_hours, weather_cut, seed, notes`, and the background arrivals labelled `real` or `synthetic`.
- **Config:** every uppercase scalar in `config.py`.
- **Assumptions:** A-FUEL-1, the 45 min spare sits on top of the 30 min reserve. A-WAKE-1, every flight is Large. A-CAP-1, arrivals get 50% of runway ops, with a 30% weather cut (17% in the sensitivity run). A-FILL-1, synthetic filler arrivals. A-COST-1, stub cost model.
- **Rules:** those ATC's stub evaluates (C-CAP-1, C-FUEL-1, and C-SEP-1 if the `check_slot` worker adds it), and those it doesn't (C-RWY-1 is out of scope; Ground and Pilot rules are team B's).

### 3.6 Readable summary (`summary.md`, fixed templates, no LLM)
Sections: run basis (one line); ATC turns (one line each); validator events; checks, FAIL and UNKNOWN first; assumptions; limits, for example "stand-in middleman and Pilot, no Ground" for the demo.

Templates; the values come from events:
- `R1 ATC proposed {source_id}: arrive {slot} via {ground} min ground delay, {hold} min holding; total system delay {tsd} min. Reason: "{reason}" [evt {id}]`
- `R2 ATC countered {P#} with {O#}: {field} {old} → {new}; …; total system delay {old} → {new} min. [evt {id}]`
- `R2 attempt 1 refused by validator: {error}. Re-asked once. [evt {id}]`
- `R3 ATC output invalid twice; recorded as reject (status ERROR). Raw outputs: {refs}`

## 4. Interfaces for teams A, B, C and D

```python
# ATC agent: team A calls it. The only addition is one optional argument.
ATCAgent(world, dry_run=False, negotiation_id=None, trace_dir: Path | None = None)
#   trace_dir default: atc-agent/runs/{negotiation_id}/{run_id}/; team A may pass its own run folder
agent.propose() -> dict                                  # unchanged
agent.respond(round_no, table, check, others) -> dict    # unchanged
agent.trace_path -> Path                                 # the run folder
agent.trace_for(message_id: str) -> dict
#   {"message_id", "attempts": [{"attempt", "input_ref", "raw", "validator_errors", "cache_hit"}],
#    "effective": {...enveloped message...}}

# Reference helpers (atc_agent/contract_log.py): team A may import them or copy them
build_log_line(message: dict, table: dict | None, check: dict | None,
               cost_usd: float | None, total_system_delay_min: float | None) -> dict  # the 10 v0.2 fields
build_outcome_line(negotiation_id: str, outcome: str, reason_code: str, rounds_used: int,
                   agent_calls: int, accepting_message_ids: list[str], final: dict | None,
                   fallback: dict | None = None) -> dict                               # §7(e), option E1
build_human_line(negotiation_id: str, decision: str, plan_id: str | None, note: str = "") -> dict
validate_log_line(line: dict) -> list[str]   # [] when keys, ids and enums match; for the UI and eval
```
For team B: ATC's stub `check_slot` output is the reference shape until B's checker lands. ATC records coverage for `ATC_EXPECTED_RULES = ("C-CAP-1", "C-SEP-1", "C-FUEL-1")`, so B's checker should emit an entry for each of them.

## 5. Implementation steps (Sonnet workers, split by file)

Start **after** the `check_slot` worker commits, and base the worker worktrees on that commit. Neither worker touches `menu.py`, `prompt.py`, `facts.py` or the contract files.

**W1: trace and wiring (MVP, about 25 min).**
- Files: new `atc_agent/trace.py` and `atc_agent/selfcheck.py`; edit `agent.py` and `demo.py`; add `runs/` to `atc-agent/.gitignore`.
- `trace.py` provides:
  - `class Trace(run_dir: Path, negotiation_id: str)` with `.artifact(obj, kind) -> str` (a relative ref), `.event(type, *, message_id, round, attempt, payload, artifact_refs=(), caused_by=None) -> str` (an event_id) and `.write_manifest(d) -> str`;
  - `plan_hash(plan) -> str`: sha256 of canonical JSON, first 16 hex characters;
  - `plan_diff(old, new) -> dict`;
  - `build_manifest(world, agent) -> dict`.
- `agent.py`: create the Trace in `__init__`; in `_turn`, emit INPUT before and OUTPUT after each attempt, INVALID on errors, and EMITTED before both returns; add `trace_path` and `trace_for`. Also fix the stale-metadata bug: on a cache hit, set `_last_meta = {"cache_hit": True, "latency_s": None, "usage": None}`. Today the previous call's latency and usage leak into the log (`agent.py:104-105, 112, 154`).
- `demo.py`: table P1 as the cheapest valid R1 proposal with `proposed_by: "atc"` (settled (c)), and print the run folder path.
- `selfcheck.py` forces two bad outputs through a monkeypatched `_stand_in`: (1) an accept with the wrong `plan_id`; (2) an accept that copies P1's values while P2 is on the table.
- Verify:
  1. Run `python -m atc_agent.demo --dry-run` and the same with `--flag EMERGENCY_FUEL`. Check that the run folder has 3 EMITTED events and that every artifact ref resolves.
  2. Run `python -m atc_agent.selfcheck`. Expect 2 OUTPUT, 2 INVALID and 1 EMITTED (status ERROR) for each forced case, with the raw text preserved.
  3. Run one live demo on cached responses: `cache_hit` should be true and the messages unchanged, which proves the cache keys are untouched.

**W2: helpers and summary (MVP, about 20 min, runs in parallel; it shares no files with W1).**
- Files: new `atc_agent/contract_log.py` and `atc_agent/summary.py`.
- It builds against the event format in §3.2 and a small hand-written fixture run folder in `atc-agent/tests/fixtures/`.
- `summary.py` provides `render_summary(run_dir: Path) -> str` and `write_summary(run_dir) -> Path`, plus a CLI: `python -m atc_agent.summary <run_dir>`.
- Verify:
  1. `validate_log_line` returns `[]` on the message-schema §5 example and catches a missing key and a bad agent value.
  2. The summary renders from the fixture.
  3. After W1 merges, render a real dry-run folder. One wiring line in `demo.py` (calling `write_summary`) is added by whoever merges second.

**W3: replay and duplicate guard (later, after 15:45).**
- Files: new `atc_agent/replay.py`; edit `agent.py` (after W1).
- `replay(run_dir) -> list[str]` rebuilds the menu as `Option(**d)` and re-runs `schema.validate` on each stored raw output, with the stored input text, flags and table. It reports any mismatch with the recorded errors or the effective message.
- Duplicate guard: a second `respond` for the same round returns the stored message and logs `ATC_DUPLICATE_CALL`.
- Optional: add a trace capability to the ATC spec (`spec-atc-agent`).
- Verify: replay reports 0 mismatches on dry-run and cached-live folders, and 1 mismatch after hand-editing one raw artifact.

## 6. Acceptance checks (the subset of logging-plan §14 that the MVP meets)

| §14 case | MVP | Test |
|---|---|---|
| The LLM says accept but a check fails: keep both records, block the acceptance | Yes (ATC side) | `selfcheck` case 1: two raw accepts plus an ERROR reject, with nothing overwritten |
| An agent accepts an earlier plan version: the acceptance doesn't transfer | Yes | `selfcheck` case 2: INVALID. The EMITTED event carries the plan hash it accepted |
| A hard rule is missing from the check report: coverage fails | Partly | `coverage.missing` is listed in EMITTED and in the summary. Refusing the plan is team A's or B's job |
| A hard check is UNKNOWN: no acceptance | Depends on `check_slot` | A plan not in the menu gives UNKNOWN, so status ERROR. Team A must not table it |
| A teammate reads only the summary | Yes (ATC turns) | Read `summary.md` from the dry-run and EMERGENCY_FUEL runs. Each line names the action, the values, the quoted reason and the diff |
| A reviewer follows a claim to its evidence | Yes | Every summary line ends with its event id; every ref resolves (W1 verify 1) |
| Failed checks stay prominent | Yes | FAIL and UNKNOWN are listed first |
| A message delivered twice counts once | Later (W3) | Call `respond(2, …)` twice; expect the same message plus a duplicate event |
| Replaying the export without an LLM reproduces the result | Later (W3) | `replay()` reports 0 mismatches |
| All accept / different plans / two accept and one rejects / R3 ends without agreement / no feasible fallback | Team A and B | Not ATC. ATC already refuses a counter in R3 |
| State changes before selection; crash during the decision write | Dropped | Static state and no database |

## 7. Decisions still needed from Ryan

**(e) How the log records the final outcome or halt. This is the main open decision.** Whatever shape is chosen, it must carry:
- `outcome`: `consensus`, `halt_least_cost` or `recommend_cancel`;
- `reason_code`: `ALL_ACCEPTED`, `NO_VALID_R1_PLAN` or `NO_CONSENSUS_AFTER_R3`;
- `rounds_used`, and `agent_calls` (counted messages plus re-asks);
- `accepting_message_ids`: exactly three, from one round, for consensus; **empty for a halt** (no invented acceptances, logging plan §9);
- the final plan's `plan_id` (P# for consensus, null for a halt), `proposed_by`, `source_id`, `plan`, `check`, `cost_usd`, `total_system_delay_min`;
- for a halt, `fallback: {candidates_enumerated, valid, selected_source_id, tie_break}`;
- then a human line (`approve` or `reject`), because `CLAUDE.md` §5 step 5 says "decision logged".

- **E1. A closing line in the same JSONL, with the same 10 keys.** `agent: "middleman"`, `message_id: "{neg}-outcome"`, `round` = the last round played, and `message` holds the outcome object. The human line uses `agent: "human"` and `message_id: "{neg}-human"`.
  - Pros: one ordered file tells the whole story, so the UI and eval read one stream. No new keys. Replaying the log alone reconstructs the outcome.
  - Cons: the `agent` enum gains two values. `message` takes two shapes, so code that reads "agent messages" must skip these lines. Two lines in the contract files change.
- **E2. A separate `outcome.json` per negotiation**, with the human decision added to it.
  - Pros: the log stays exactly "one line per agent message" (CAP-8 untouched). The doc crafter and the eval table read one simple object.
  - Cons: two files must travel together, with no shared order. It looks close to the `FinalResult` object v0.2 rejected. The log alone no longer shows how the negotiation ended.
- **E3. Add an 11th key, `line_type` (`agent_message`, `outcome` or `human_decision`), to every line.**
  - Pros: explicit and extensible (FALLBACK_STARTED could be added later).
  - Cons: changes the committed 10-field line for every lane right at freeze time; every reader and validator needs updating.
- **E4. No outcome record; derive it.** Three accepts of one P# mean consensus; anything else means halt.
  - Pros: zero work.
  - Cons: the fallback plan, its cost and its trigger never appear in the log, which fails "traceable consensus log" and honest fallback. The human decision has nowhere to go, and the derived result can disagree with what the middleman actually did.
- **Recommendation: E1**, built with `build_outcome_line` and `build_human_line` (§4). Team A writes the lines. If team A won't widen the `agent` enum, use E2: it is the least-bad alternative. Either way, the outcome can't be omitted.

**(g) New: ship the logging after the 15:00 freeze?** The workers would land around 15:20.
- Option 1: allow W1 and W2 as a "traceability, no behaviour change" exception. Pros: big gain on trust and traceability. Cons: risk to the demo, plus rehearsal time.
- Option 2: W1 only. Pros: half the risk. Cons: no readable summary.
- Option 3: none. Cons: delivered inputs stay unrecorded.
- **Recommendation: Option 1.** Gate it: if the cached demo doesn't replay identically by 15:30, revert.

**(h) New: commit one sample run folder as judge-visible evidence?** `runs/` is gitignored.
- Option 1: commit one dry-run and one cached-live run under `atc-agent/docs/sample-run/`. Pros: judges can open them. Cons: a few hundred KB of repo noise.
- Option 2: keep it local and demo it live. Cons: lost if the laptop or session fails.
- **Recommendation: Option 1**, curated, with no keys in it (there are none in the trace).

**(i) New: trace on by default?**
- Option 1: always on. Pros: evidence is never missing. Cons: disk writes per call, which are trivial.
- Option 2: a `--trace` flag. Cons: someone forgets it during the batch eval.
- **Recommendation: Option 1.**

## 8. Risks and honest limits

- **Integrity:** these are plain files. Content hashes catch accidental changes to artifacts referenced by hash. Anyone with disk access can still rewrite events and recompute the hashes. Claim "traceable and replayable", never "tamper-proof".
- **Stand-ins:** the demo uses a stand-in middleman and Pilot, and has no Ground. `summary.md` must say so. The three-agent trail depends on team A.
- **Stub checker:**
  - `check_slot` is ATC's stub, and team B's checker is authoritative.
  - Menu options are valid by construction, so C-CAP-1 and C-SEP-1 PASS results partly restate how the menu was built. They are a consistency check, not independent verification.
  - If C-SEP-1 is not added to `check_slot`, coverage shows it as missing, openly.
- **Cache invalidation:** the `check_slot` change alters the "CHECKER RESULT" text in R2 and R3, so cached R2/R3 responses miss. After that commit, run the live demo once and re-rehearse: wording, and possibly the actions, may change.
- **Wrong latency today:** on a cache hit, the per-call log carries the previous call's latency and usage. Eval latency figures are wrong until W1 lands.
- **Inputs:** `flights.csv` is identified by size and mtime only. The trace uses local time plus UTC.
- **Fuel:** the logging plan's §7 and §12 examples assume 45 min *includes* the 30 min reserve. Ours puts it *on top*, so the manifest states A-FUEL-1 explicitly. Don't quote the plan's 20-min example.
- **Schema drift:** commit `46b00a9` on origin/main ("shared message schema") hasn't been inspected. Check it before W1 and W2 start; if it competes with v0.2, settle that first.
