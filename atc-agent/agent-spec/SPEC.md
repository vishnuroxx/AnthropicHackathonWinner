---
id: SPEC-atc-agent
companions:
  - private-state.md
  - icap.md
  - research.md
  - agent-contract/SPEC.md
  - agent-contract/message-schema.md
  - agent-contract/rule-registry.md
  - ../../CLAUDE.md
  - ../../data/raw/challenge2/challenge-2-operational-constraints.xlsx
sources:
  - ATC_Agent_ICAP_Analysis.md (Ryan, local file; condensed into icap.md)
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# ATC Agent

Scope: the ATC agent only. Team workflow (§5), checker (§8), cost (§9) and fallback (§10) are in `CLAUDE.md`; the message schema is §7 as extended by `agent-contract/`. Numeric limits come from the organiser workbook.

## Why

Pain to solve. In a weather or late-aircraft disruption, air traffic control decides when the focal flight lands. It owns separation and throughput, and it speaks for the background flights that share the arrival slots. The ATC agent argues those interests in the three-agent negotiation (Airbus Challenge #2). It aims at the lowest total system delay without pushing delay onto others, and it never trades safety for delay or fuel. Its interests, constraints, alternatives and perspective follow Ryan's ICAP analysis (`icap.md`), which no ATC practitioner has validated yet.

## Capabilities

- **CAP-1**
  - **intent:** ATC reasons from the event plus its own facts (`private-state.md`) and nothing else.
  - **success:** The ATC prompt contains the event, the focal flight's real row fields and ATC facts only. It contains no Pilot or Ground facts and no outcome columns.
- **CAP-4**
  - **intent:** In round 1, ATC proposes one arrival option for the focal flight from the code-computed option menu: a slot reached by ground delay or airborne holding, with the least total system delay.
  - **success:** The proposal names a menu option id, and its `arrival_slot`, `ground_delay_min` and `holding_min` equal that option's values and pass the checker's slot check.
- **CAP-6**
  - **intent:** ATC states only facts that match its private state, in the schema's short fields.
  - **success:** Every number in `need`, `offer` and `reason` appears in ATC's facts or menu. Word limits hold (≤ 20 / 20 / 30).
- **CAP-7**
  - **intent:** In rounds 2–3, ATC responds to the table plan: accept or reject, and in round 2 only, counter with a different menu option.
  - **success:** Each reply is a valid schema message. An accept echoes the table `plan_id` (P#). A counter appears only in round 2 and carries a full plan from the menu. Round 3 allows accept or reject only. `reason` cites a constraint or fact.
- **CAP-8**
  - **intent:** ATC handles fuel flags as the FAA does. A `MINIMUM_FUEL` flag means no undue delay, not priority. An `EMERGENCY_FUEL` flag means priority.
  - **success:** After `MINIMUM_FUEL`, ATC never proposes or accepts a plan that adds holding or a later slot for that flight. After `EMERGENCY_FUEL`, ATC proposes the earliest valid menu option.
- **CAP-9**
  - **intent:** ATC speaks for the passive background flights.
  - **success:** ATC counters a plan whose knock-on delay exceeds that of a cheaper valid menu option, citing the knock-on.
- **CAP-10**
  - **intent:** ATC prefers a stable plan over churn.
  - **success:** ATC accepts a valid table plan unless its own best menu option has `total_system_delay_min` at least 5 lower (`CAP10_TOLERANCE_MIN`); a 1-min gain does not justify a counter. It then counters in round 2 or rejects in round 3. `EMERGENCY_FUEL` overrides the tolerance.
- **CAP-11**
  - **intent:** ATC is cautious about plans at the capacity edge.
  - **success:** When the chosen option leaves no spare arrival slot in its hour, ATC's `need` or `reason` names the thin margin.

## Constraints

- **Limits precedence:** the organiser workbook overrides `CLAUDE.md` wherever they differ (wake separation, runway capacity, gates, fuel reserve, spare fuel, crew limits, gate-change notice). Any workbook limit we change is stated in the demo.
- **Safety is hard:** wake separation and arrival capacity are checker constraints; a plan that breaks one is invalid and is never priced against delay or fuel.
- **Menu only:** code computes every number (slots, delays, spacing, knock-on, cost, spare slots). ATC picks a menu option by id and argues; it does no arithmetic or legality checks.
- **Other agents' claims are inputs:** Pilot and Ground statements inform ATC, but only the checker decides validity.
- **Jurisdiction:** ATC decides arrival time only. Divert is Pilot-only; gate is Ground's.
- **Message flow:** one ATC call per round, separate from Pilot and Ground, at most 3 per scenario. Schema and rounds as in `agent-contract/` (hybrid v0.2: `CLAUDE.md` §5 and §7 body, plus a code-filled envelope). `flags` is a closed enum `{MINIMUM_FUEL, EMERGENCY_FUEL}`; the validator rejects any other value.
- **No hindsight:** ATC never sees `DEPARTURE_TIME`, `ARRIVAL_TIME`, `ARRIVAL_DELAY`, `DEPARTURE_DELAY`, `WHEELS_ON/OFF`, `ELAPSED_TIME`, `AIR_TIME` or `TAXI_IN/OUT`.
- **Labelled values:** every value is labelled real, derived, synthetic or organiser. Synthetic parameters (`private-state.md`) live in config, not in prompts.
- **Provisional ICAP:** no ICAP interest, constraint or perspective is presented as practitioner-confirmed. No invented minima, weights, time limits or capacities beyond `private-state.md`.

## Non-goals

- Team workflow pieces: middle man, checker, cost model, fallback solver, document crafter, UI.
- Pilot and Ground agents.
- Runway or taxiway closure, pushback conflicts, equipment, crew or security events.
- Re-sequencing background flights (no schema field).
- External parties: adjacent facilities, flow-management units, airport operator, airline dispatch.
- ATC's own utility weights or concession bounds.
- Cancellation (a recommendation to the human only).
- A practitioner validation workflow for the ICAP.

## Success signal

- On the demo scenario (DFW, 24 Apr 2015 weather), the ATC agent returns a valid schema message each round. In round 1 it proposes a menu option that passes the slot check. In rounds 2–3 it accepts or counters with a cited reason. It applies FAA fuel handling to a forced `MINIMUM_FUEL` case and a forced `EMERGENCY_FUEL` case, and it never states a number outside its facts or menu.

## Assumptions

- ICAP ranks nothing beyond safety first. The ATC prompt keeps safety first and does not rank throughput, workload, stability or option-keeping.
- ICAP scope: ATC is a combined approach and flow-management representative for arrivals at the focal destination, under FAA rules as simplified by the workbook, with a horizon of the focal hour ± 1 h.
- ICAP A5 (controller-led procedure without agreement) maps to the deterministic fallback.

## Open Questions

- Should ATC see the fallback plan as its walk-away reference (ICAP Alternatives)?
- Is any ATC practitioner available to validate the ICAP? Every item is currently `Pending`.
- Team: does team B take over the synthetic filler arrivals, and will the team accept the `EMERGENCY_FUEL` flag in the `CLAUDE.md` §7 contract?
- Must the contract (`agent-contract/`) move into `docs/challenge-2-framing.md` §4–5 in its own commit with the team told, as `CLAUDE.md` requires? Who does it?
