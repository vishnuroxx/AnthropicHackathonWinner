# ATC ICAP (condensed, MVP-mapped)

Source: Ryan's ICAP analysis (Malhotra, *Negotiating the Impossible*, ch. 16: Interests, Constraints, Alternatives, Perspective). **Every item is `Pending`**: no ATC practitioner has confirmed it.

Basis labels: **brief** = stated in the challenge · **source** = general principle in cited material · **inferred** = plausible, unconfirmed · **scenario** = depends on facts not supplied.

## Scope (ICAP §3 unknowns, fixed for the MVP)

| Question | MVP answer |
|---|---|
| Which ATC role | Combined approach + flow-management representative for arrivals |
| Airport, rules | Focal destination (demo: DFW); FAA rules as simplified by the organiser workbook |
| Disruption, horizon | Weather or late aircraft; focal hour ± 1 h |
| Pilot/Ground authority | Pilot = focal flight only; Ground = gates and crew at the destination (`CLAUDE.md` §7) |

## Interests

| ID | Interest | Basis | MVP mapping |
|---|---|---|---|
| I1 | Separation and movement safety | source | Hard checker constraint (wake, capacity); never priced |
| I2 | Orderly flow, efficient use of capacity | brief, source | Objective: lowest total system delay (CAP-4, CAP-9) |
| I3 | Manageable workload | inferred | Prompt preference: fewer changes (CAP-10) |
| I4 | Stable, predictable plan | inferred | CAP-10: accept a valid table plan unless the best option is cheaper |
| I5 | Preserve options for further disruption | inferred | CAP-11: name a thin margin when no spare slot is left |
| I6 | Reliable shared information | source | Reasons cite facts (CAP-6) |

Priority: safety first. The I2–I6 ranking is unvalidated, so the prompt doesn't rank them.

## Constraints

| ID | Constraint | Basis | MVP mapping |
|---|---|---|---|
| C1 | Wake and runway separation | brief, source | Workbook `wake_separation` → checker (hard) |
| C2 | Runway/taxiway availability | brief, source | Non-goal (no closure events) |
| C3 | Traffic and facility capacity | source, scenario | Workbook capacity + weather cut → checker (hard) |
| C4 | Aircraft capability, pilot limits | source | Pilot's facts; ATC treats them as inputs, the checker decides |
| C5 | Priority and fuel status | source | CAP-8: `MINIMUM_FUEL` = no undue delay; `EMERGENCY_FUEL` = priority (FAA JO 7110.65 §2-1) |
| C6 | Jurisdiction, resource ownership | source, scenario | ATC sets arrival time only; gate = Ground, divert = Pilot |
| C7 | Time available, picture reliability | inferred, scenario | Non-goal |

The agent must not treat a preference as a hard constraint, or negotiate away a hard requirement.

## Alternatives (what happens without agreement)

| ID | Alternative | Basis | MVP mapping |
|---|---|---|---|
| A1 | Continue existing plan where valid | scenario | The original slot is a menu option when it stays valid |
| A2 | Restrict demand via flow measures (ground stop, ground delay program) | source | Ground-delay lever |
| A3 | Holding or resequencing | scenario | Holding lever; resequencing is a non-goal |
| A4 | Different runway, route or diversion | scenario | Diversion is the Pilot's; runway choice is a non-goal |
| A5 | Controller-led procedure | inferred | Deterministic fallback (`CLAUDE.md` §10) |

## Perspective (hypotheses to test)

| ID | Perspective | Basis | MVP mapping |
|---|---|---|---|
| P1 | Whole traffic picture | source | Knock-on per option in the menu |
| P2 | Executable plans only | source | Menu options only |
| P3 | Predictions ≠ commitments | source | Other agents' claims are inputs; the checker decides |
| P4 | Workload of changing the plan | source | CAP-10 |
| P5 | Caution with optimistic assumptions | source | CAP-11 |
| P6 | Understandable reasoning | source | `reason` cites a constraint or fact |

## Rules carried from ICAP §11

- Keep items provisional until validation is recorded.
- Keep basis labels distinct; never present an inference as a practitioner view.
- Never invent minima, weights, time limits, capacities or authority.
- Record a validation outcome as `Confirmed`, `Corrected`, `Rejected` or `Unresolved`, with the reviewer's role, scope and evidence. A confirmation holds only for its stated role and scenario.
- When source and practitioner conflict, keep the discrepancy open.

## Source references

S1 challenge brief · S2 Malhotra ch. 16 · S3–S4 CAAS ATC services and A-CDM · S5 FAA JO 7110.65 ch. 2 §1 (duty priority, minimum fuel) · S6 FAA wake turbulence · S7 JO 7110.65 ch. 3 §3 · S8 JO 7110.65 ¶2-1-14/15 · S9 AIM ch. 5 §5 · S10 FAA ground stops · S11 EUROCONTROL SHAPE · S12 IFATCA/EUROCONTROL 2024.
