---
id: SPEC-atc-agent
companions:
  - private-state.md
  - research.md
  - ../../../CLAUDE.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# ATC Agent

Scope: the ATC agent only. The agreed MVP scope in `CLAUDE.md` is the authority: workflow (§5), world state (§6), agents and message schema (§7), checker (§8), cost model (§9), fallback (§10). This spec does not restate the team workflow.

## Why

Pain to solve. In a weather or late-aircraft disruption, air traffic control decides when the focal flight lands. It owns throughput and separation, and it speaks for the background flights that share the arrival slots. The ATC agent argues those interests in the three-agent negotiation (Airbus Challenge #2), aiming at the lowest total system delay rather than pushing delay onto others.

## Capabilities

- **CAP-1**
  - **intent:** ATC reasons from the event plus its own facts (`private-state.md`) and nothing else.
  - **success:** The ATC prompt contains the event, the focal flight's real row fields and ATC facts only; no Pilot or Ground facts and no outcome columns (CLAUDE.md §6 "No hindsight").
- **CAP-4**
  - **intent:** In round 1, ATC proposes its preferred arrival time for the focal flight: a slot reached by ground delay or airborne holding that fits the reduced capacity and spacing, with the least total system delay.
  - **success:** The proposal sets `arrival_slot`, `ground_delay_min` and `holding_min` from code-computed facts, and passes the checker's slot check.
- **CAP-6**
  - **intent:** ATC states only facts that match its private state, in the schema's short fields.
  - **success:** Every fact in `need`, `offer` and `reason` matches ATC's facts; word limits hold (≤ 20 / 20 / 30).
- **CAP-7**
  - **intent:** In rounds 2–3, ATC responds to the table plan with accept or counter (a different slot or a re-sequence).
  - **success:** Each reply is a valid schema message; a counter carries a full plan; `reason` cites a constraint or objective.
- **CAP-8**
  - **intent:** ATC prioritises the focal flight when the Pilot flags `MINIMUM_FUEL`.
  - **success:** After a `MINIMUM_FUEL` flag, ATC never proposes or accepts a plan that adds holding to that flight.
- **CAP-9**
  - **intent:** ATC speaks for the passive background flights.
  - **success:** ATC counters or rejects plans whose knock-on delay to background flights exceeds a cheaper valid alternative, citing that knock-on.

## Constraints

- Message schema, round structure and checker are as in `CLAUDE.md` §5, §7, §8.
- Code computes every number (slots, delays, spacing, cost); the LLM argues and explains. No arithmetic or legality checks in the prompt.
- One ATC call per round, separate from Pilot and Ground; at most 3 calls per scenario.
- ATC never sees outcome columns (`DEPARTURE_TIME`, `ARRIVAL_TIME`, `ARRIVAL_DELAY`, `DEPARTURE_DELAY`, `WHEELS_ON/OFF`, `ELAPSED_TIME`, `AIR_TIME`, `TAXI_IN/OUT`).
- ATC decides arrival time only; divert is Pilot-only, gate is Ground's.
- Every value is labelled real, derived or synthetic.

## Non-goals

- Team workflow pieces: middle man, checker, cost model, fallback solver, document crafter, UI.
- Pilot and Ground agents.
- Taxiway or runway closure, equipment, crew or security events.
- ATC's own utility function or concession bounds (the shared cost model decides cost).
- Cancellation (a recommendation to the human only).

## Success signal

- On the demo scenario (DFW, 24 Apr 2015 weather), the ATC agent returns a valid schema message each round: a round-1 slot proposal that passes the slot check, accept or counter in rounds 2–3 with a cited reason, prioritises a `MINIMUM_FUEL` flight, and never states a number that code did not compute.

## Open Questions

- Spacing per weight class: CLAUDE.md gives regional vs mainline but no values — which minutes/NM per pair?
- Round-1 full plan: does ATC fill `gate`, `extra_fuel_min`, `divert` with defaults (current gate, 0, false)?
- ATC facts: delivered via tools or injected into the prompt (CLAUDE.md §7 allows both)?
- `MINIMUM_FUEL` priority: earliest valid slot, or just no added holding?
- Delay-type ownership (ATC reduces AIR_SYSTEM and WEATHER delay) is not in the agreed scope — keep as an ATC interest or drop?
- `docs/challenge-2-framing.md` contradicts CLAUDE.md (message schema, rule IDs, no divert, concede step) — flag to the team which is current?
