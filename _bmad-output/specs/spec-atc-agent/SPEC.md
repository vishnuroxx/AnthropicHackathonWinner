---
id: SPEC-atc-agent
companions:
  - private-state.md
  - research.md
  - ../../../docs/challenge-2-framing.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# ATC Agent

Scope: the ATC agent only. The general flow (option generator, mediator, turns, agreement rule, fallback, checker, consensus log, UI) is team-owned and defined in `docs/challenge-2-framing.md`; this spec does not restate it.

## Why

Pain to solve. In a disruption, air traffic control decides who lands when. It owns runway safety (wake separation, closed runways and taxiways) and arrival throughput, and it holds the runway and sequence picture the airline and ground ops don't see. The ATC agent argues those priorities in the three-agent negotiation (Airbus Challenge #2): it must take care of runway wake separation and taxiway blockage, and maximise sector throughput.

## Capabilities

- **CAP-1**
  - **intent:** ATC agent reasons from the shared scenario plus its own private state (`private-state.md`) and nothing else.
  - **success:** The ATC prompt contains the shared scenario, the candidate options and ATC private state only; no Pilot or Ground private field appears in it.
- **CAP-2**
  - **intent:** ATC ranks candidate options by its own utility (throughput vs arrival capacity, airborne holding, ripple on the landing queue, owned delay minutes), computed by code.
  - **success:** Every ranking cites metrics returned by the ATC utility tool; the LLM performs no time, delay or capacity arithmetic.
- **CAP-3**
  - **intent:** ATC objects to options that break the runway rules it cares about (C-WAKE-1, C-SEP-1, C-RWY-1), tied to rule and evidence IDs.
  - **success:** Every ATC objection carries a valid `rule_ref` and `evidence_ids` that exist in the scenario.
- **CAP-4**
  - **intent:** ATC proposes slot or holding changes that fit arrival capacity with the least ripple on other arrivals.
  - **success:** ATC proposals change only `slot` or `hold_min`, and each is re-checked by code (pass, or veto with rule ID).
- **CAP-5**
  - **intent:** When it must, ATC concedes by relaxing one of its stated preference bounds.
  - **success:** Each concession names an ATC preference and a new bound within the range allowed in code.
- **CAP-6**
  - **intent:** ATC chooses which private facts to reveal and never states false information.
  - **success:** Every fact ATC states (e.g. "capacity 40/h until 16:00") matches its private state.

## Constraints

- Messages follow the team contract (`docs/challenge-2-framing.md` §4); rule IDs come from §5. Change them only there.
- Code computes every number (times, delays, capacity, utility); the LLM argues and explains.
- ATC never receives Pilot or Ground private state.
- Wake separation uses ICAO Doc 4444 values on US data, disclosed; the 3 NM minimum (C-SEP-1) is a stated assumption.
- Every value shows its provenance: real, enriched or synthetic (seeded, labelled).

## Non-goals

- Team-owned flow: option generator, mediator, turns, agreement rule, fallback, constraint checker, consensus log, UI.
- Pilot and Ground agents, and the rules they own (fuel, gates, turnaround, crew, connections).
- Diversion and cancellation options (none in the data).
- RECAT/CWT wake categories, time-based departure separation, real ATC systems.

## Success signal

- Given a real 2015 disruption scenario, the ATC agent returns a valid contract message every turn: it ranks options using code-computed utility, vetoes a wake- or taxiway-violating option with the correct rule ID, and concedes or accepts without inventing any number.

## Open Questions

- ATC utility: exact components and weights?
- ATC preference bounds it can concede on (e.g. max hold minutes, max arrivals per hour)?
- The contract has no field for revealed facts — put them in `rationale_short`, or add a field (team change)?
- The contract's change field lists `divert`, but diversion is out of scope — confirm ATC never proposes it.
- Is the landing queue truly ATC-private? In reality airlines see arrival demand in the FAA Flight Schedule Monitor (`research.md` A7).
- Delay-type ownership (ATC reduces AIR_SYSTEM and WEATHER delay minutes) came from the earlier spec and is not in the team framing — keep it in ATC utility?
