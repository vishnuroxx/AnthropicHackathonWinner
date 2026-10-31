---
id: SPEC-agent-contract
companions:
  - message-schema.md
  - rule-registry.md
  - ../../../../CLAUDE.md
  - ../../../../docs/challenge-2-framing.md
  - ../../../../data/raw/challenge2/challenge-2-operational-constraints.xlsx
sources:
  - ATC_Agent_Contract_v0_1.md (Ryan, local file; partly rejected, see Non-goals)
---

> Copied from ../../spec-agent-contract/ on 2026-10-31; source of truth is there.

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Agent Message Contract v0.2 (hybrid)

Scope: the message shape shared by the ATC, Pilot and Ground agents, the middleman, the checker, the UI and the evaluator. Flow (`CLAUDE.md` §5), cost model (§9) and fallback (§10) are unchanged. Status: a proposal until the contract moves into `docs/challenge-2-framing.md` §4–5 (Open Questions).

## Why

Mandate and pain. Four lanes (agents, middleman, checker, UI/eval) build in parallel against one message shape, and the brief demands structured messages, explicit constraint checking and a traceable consensus log. `CLAUDE.md` §7 fixes only the agent-written body, so ids, validity, errors and log lines are undefined; each lane would invent its own and the 15:00 feature freeze would meet mismatched pieces. This contract wraps §7's LLM-written body in code-written ids and checks, so no model ever asserts validity or states a number. It is the smallest change to §7 that makes a three-agent negotiation runnable and auditable.

## Capabilities

- **CAP-1**
  - **intent:** Each agent states its position as one short structured message in the fields `CLAUDE.md` §7 defines.
  - **success:** A validator accepts a message body only if its fields, types and word limits (`need` ≤ 20, `offer` ≤ 20, `reason` ≤ 30) match `message-schema.md`, `arrival_slot` is HH:MM and every other plan time is a `_min` field. An unknown body field fails validation (envelope keys are discarded first, CAP-2).
- **CAP-2**
  - **intent:** The middleman identifies every agent message by negotiation, message and ruleset, so any log line can be traced and replayed.
  - **success:** Every logged agent message carries all seven envelope fields, with ids built by the formulas in `message-schema.md` (for example `DFW-20150424-MQ3086` and `DFW-20150424-MQ3086-r2-atc`). Envelope values the LLM emits are discarded. `state_revision` is 0 and `ruleset_id` is `challenge2-workbook-2026-10-31` throughout the MVP.
- **CAP-3**
  - **intent:** Code, not the LLM, states whether a plan is valid, with rule ids and measured values as the evidence.
  - **success:** Every table plan and every logged message carries a check with status `VALID | INVALID | ERROR` and one entry per evaluated rule (`rule_id`, result `PASS | FAIL | UNKNOWN`, `actual`, `limit`, `unit`). Every `rule_id` exists in `rule-registry.md`. A plan with a hard FAIL is INVALID and never reaches the table. No LLM-written field states validity.
- **CAP-4**
  - **intent:** Each plan on the table has one unambiguous id, so an accept means exactly one checked plan.
  - **success:** The middleman assigns P1, P2, … only to plans it puts on the table, and each table plan carries `plan_id`, `proposed_by`, `source_id`, `plan`, `check`, `cost_usd` and `total_system_delay_min`. Agents propose and counter under their own local id (ATC uses O#). An accept whose `plan_id` differs from the current table's P# is invalid output.
- **CAP-5**
  - **intent:** A middleman can run a negotiation of at most three rounds with three agents and decide its outcome using only contract fields.
  - **success:** R1 is propose; R2 is accept, counter or reject; R3 is accept or reject, and a counter in R3 is invalid output. Consensus is declared only when all three agents accept the same table `plan_id` in R2 or R3. Otherwise, or when R1 yields no valid plan, the middleman halts and the deterministic least-cost fallback decides. No scenario exceeds 3 rounds or 9 agent messages.
- **CAP-6**
  - **intent:** An agent can declare its fuel state from a fixed set whose meanings follow FAA practice.
  - **success:** `flags` holds only `MINIMUM_FUEL` and `EMERGENCY_FUEL`; any other value fails validation. `MINIMUM_FUEL` means no added holding and no later slot than the table plan, and gives no priority. `EMERGENCY_FUEL` means landing fuel would breach the 30-min final reserve, and requires the earliest valid slot.
- **CAP-7**
  - **intent:** A bad agent output cannot stall or silently corrupt a negotiation.
  - **success:** Output that is unparseable or invalid is re-asked once. If it is still bad, the middleman records `action: reject`, status `ERROR` and the listed `validator_errors`, and the round continues with the other agents' messages. There is no second re-ask.
- **CAP-8**
  - **intent:** Every agent message leaves one line in a log that the UI and evaluator read without the agents.
  - **success:** Each agent message yields one JSONL line with the ten fields in `message-schema.md`; `message` is the full enveloped message and the line's `negotiation_id` and `message_id` equal the envelope's. The UI and evaluator can rebuild each round's table plan, replies and checks from the lines alone.

## Constraints

- **Code fills, the LLM states:** envelope, plan ids `P#`, check, cost and every number come from code. An LLM output never supplies them; the validator discards or rejects them.
- **Body unchanged:** agent-written fields stay exactly those of `CLAUDE.md` §7, so existing consumers keep working. All additions are code-side.
- **Round budget:** one message per agent per round, at most 3 rounds and 9 agent messages (`CLAUDE.md` §5; workbook `rules_of_play`). A re-ask is the only extra call. R3 allows no counters.
- **Invalid plans stay private:** a plan with a hard FAIL never reaches the table or another agent; only its proposer sees the violations.
- **Limits precedence:** the organiser workbook overrides `CLAUDE.md` and the framing doc wherever they differ (`rule-registry.md`). Any workbook limit we change is stated in the demo. Rule values live in checker config, not in prompts.
- **Units:** plan and message times are minutes with a `_min` suffix; slots are HH:MM local. A check entry names its own unit.
- **Stable ids:** rule ids and capability ids are never reused or renumbered; new rule ids enter through `rule-registry.md` only.
- **Governance:** `CLAUDE.md` places contracts in `docs/challenge-2-framing.md` §4–5, changed in their own commit with the team told. Until then this spec is a proposal and the framing doc stays unedited.

## Non-goals

- A shared candidate catalogue that every agent evaluates (v0.1). The middleman tables one checked plan at a time.
- Acceptance-set intersection as the consensus rule. Consensus is all-accept on one table plan.
- Times in seconds in message or plan fields.
- Runway or taxi plan fields. The plan carries arrival slot, delays, fuel, gate and divert only.
- A `FinalResult` object (v0.1).
- A transport or HTTP mapping. The payload is the contract; each lane picks its transport.
- An agent's internal inputs and option menus; each lives in that agent's own spec.
- The cost model, the fallback solver and the checker's rule logic (`CLAUDE.md` §8–10, team B). This spec fixes only what they emit.
- Runway closure, equipment, crew or security events, and live state changes (`state_revision` stays 0).

## Success signal

- The ATC demo emits messages whose bodies validate against this schema. Every log line carries an envelope. A middleman can run R1–R3 with three agents using only these fields.

## Assumptions

- The 45-min spare fuel is on top of the 30-min final reserve, so a plan may hold up to 45 min plus any extra fuel loaded before touching the reserve.
- `C-CAP-1`, `C-GATE-2` and `C-CREW-2` are new rule ids for workbook values the framing doc had no id for.
- `state_revision` stays 0: world state is static per negotiation.
- Check status: INVALID if any hard rule FAILs; ERROR if the checker raises or cannot evaluate a hard rule (UNKNOWN); VALID otherwise. A soft rule (`C-CREW-1`) reports FAIL in `checks` but never sets INVALID; its cost goes in `cost_usd`. Ryan did not state this.
- `violations` entries are strings starting with the rule id.
- `proposed_by` is `atc`, `pilot`, `ground`, or `fallback` when the deterministic solver supplies the plan (as the ATC demo does for P1). `source_id` is the proposer's own local id.
- `plan` is required on propose, counter and accept (accept echoes the table plan) and null on reject. ATC leaves `gate` null and `divert` false; code fills both in the table plan.
- Separation checks (`C-WAKE-1`, `C-SEP-1`) report seconds, a sub-minute exception to the minutes rule, because the limits are 77–206 s.

## Open Questions

- Will the team accept contract v0.2 (agents, middleman, checker, UI/eval lanes)?
- Who moves the contract into `docs/challenge-2-framing.md` §4–5, in its own commit with the team told?
- Will the Pilot and Ground lanes adopt the closed flag enum, the R3 no-counter rule and the envelope split?
- How does the log record the outcome (consensus in round N, or halt with the fallback plan)? No closing-line shape is defined and a `FinalResult` object is rejected.
