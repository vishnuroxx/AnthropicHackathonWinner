# Challenge #2 framing: negotiated disruption recovery

Synthesis of four research reports (domain and constraints, literature, Claude implementation, data and evaluation), written 31 Oct 2026. The brief and rubric are in `docs/challenge-2-brief.md`. Where reports disagreed, the choice made is noted.

## Change log
**31 Oct, after the organisers' data arrived.** The research assumed the full 5.8M-row 2015 DOT dataset. The organisers provided a **pre-filtered 358,774-row subset** containing only rows that meet the brief's delay filter. As a result:
1. **The scenario bank is the real delayed arrivals at an airport-hour**, not all traffic. On-time background traffic, if used, is seeded synthetic (§6). *Why:* on-time flights aren't in the data.
2. **Tail rotations are partial** (144,746 linked delayed-leg pairs). Missing next legs are synthesised, and the do-nothing baseline cascade uses linked pairs plus synthesised legs (§7). *Why:* a tail's on-time legs are missing.
3. **No diversion or cancellation options.** *Why:* the data has none to ground or evaluate them.
4. **Times are zero-padded strings with `2400`**; no October and no numeric airport codes, so that handling was dropped. *Why:* the export differs from the Kaggle version.
5. **Reconciled conflicts between reports:** 3 NM minimum separation is a stated assumption (ICAO default 5 NM); 25 kg/min holding burn is the default (~38 kg/min upper bound); ICAO values are used on US data, and this is disclosed.
## 1. Problem statement

**User.** An airline Operations Control Centre (OCC) duty manager at a US hub. When capacity drops, they coordinate with the FAA traffic management coordinator (TMC) and the ramp / ground-handling supervisor.

**Today.** When weather or a late aircraft disrupts an arrival bank, the FAA lowers the airport arrival rate and issues a ground stop or Ground Delay Program. The airline, tower and ramp then sort out *who lands when, at which gate, with which crew* through planning telcons, phone and radio. Each existing tool optimises one stakeholder: AMAN/DMAN sequence runways for ATC, A-CDM (Airport Collaborative Decision Making) shares milestones, Skywise covers airline data. None negotiates the ATC, pilot and ground trade-off jointly with an audit trail. That last point is our inference, not a sourced claim.

**Cost of the status quo.**
- US airline block time costs **$98.41/min** (Airlines for America, 2025).
- Delay absorbed **airborne costs about twice as much as at the gate**: an A320 with 15 min of delay costs €1,187 in airborne arrival management vs €594 at the gate (Eurocontrol standard inputs, 2022 prices).
- **Reactionary delay is 46% of European delay minutes** (Eurocontrol 2024), and **late-arriving aircraft is the largest US delay cause** at 10.16% of flights (BTS, Aug 2026).
- An A320 burns about **25 kg of fuel per minute holding** (Airbus).

**Our problem statement.** *When a disruption hits an arrival bank, the OCC duty manager needs ATC, flight-deck and ground constraints reconciled into one safe, agreed recovery plan in minutes rather than a round of phone calls, with every decision traceable to a rule or a data point.*

**What we build.** Three independent Claude agents (ATC, Pilot, Ground) negotiate over **solver-generated, rule-checked recovery options** for a real 2015 disruption. They must agree in at most 3 turns, otherwise a deterministic fallback decides. Every message, veto and decision is logged.

**Out of scope, and said so.** Live operations, real gate layouts, crew legality under FAA Part 117, time-based departure separation, RECAT/CWT wake categories. The duty manager keeps final authority: the system *recommends* an agreed plan.

## 2. Architecture

The design follows the LLM-Modulo pattern (Kambhampati 2024): the LLM proposes, sound critics verify. It also follows Anthropic's evaluator-optimizer workflow, with a deterministic evaluator.

```
DOT row ─► Scenario builder (real flights at that airport-hour + enrichment + seeded synthetic)
               │
               ▼
        Option generator (code: greedy / CP-SAT) ─► K candidate recovery options,
               │                                     each with code-computed metrics
               ▼
   ┌──── Mediator (deterministic Python: turns, termination, agreement rule) ────┐
   │      ▲            ▲            ▲                                            │
   │   ATC agent    Pilot agent   Ground agent   (3 separate Claude calls,       │
   │   (private     (private      (private        private state, typed JSON)    │
   │    runway/      fuel/         gates/crew)                                  │
   │    sequence)    connections)                                               │
   │      ▼            ▼            ▼                                            │
   │   Constraint checker (code, rule IDs) ── vetoes unsafe proposals/accepts    │
   └──────────────┬──────────────────────────────────────────────────────────────┘
                  ├─ consensus ──► Agreed plan + explanation
                  └─ no consensus / API error / malformed ──► Deterministic fallback
   Every step ─► append-only JSONL consensus log ─► timeline UI
```

**What Claude does and what code does.** This split is what the rubric scores under technical soundness.

| Claude (LLM) | Code (deterministic) |
|---|---|
| Reads its role's private state and argues its priorities | Builds the scenario, computes all times, delays, fuel and costs |
| Ranks options, accepts or rejects with reasons tied to rule/evidence IDs | Generates the feasible option set (greedy or CP-SAT) |
| Proposes modifications (e.g. "slot +1 for UA123") that code re-checks | Checks every constraint and vetoes with a rule ID |
| Explains the agreed plan to the duty manager | Owns turns, termination, the agreement rule and the fallback |

## 3. Negotiation protocol

The protocol combines Contract Net, monotonic concession (Endriss 2006) and a hard turn cap.

1. **Turn 1, bid.** The mediator broadcasts the disruption and K options. Each agent returns `RANK` (an ordered list plus objections tied to rule/evidence IDs) or `PROPOSE` (a modification to an option).
2. **Code step.** Proposals are rebuilt as options and checked. Any option that fails the checker is removed, with the reason sent back to all agents.
3. **Turn 2, concede.** Each agent must accept something or **concede** (relax a stated preference bound). Not conceding counts as a final reject.
4. **Turn 3, final.** Each agent sends `ACCEPT{option_id}` or `REJECT`.
5. **Agreement rule (code).** Among options that pass the checker and that all three agents accept, choose the one that maximises the minimum agent utility. Utility weights live in code, not in the LLM. **If no such option exists, run the fallback.**
6. **Per-turn delay cost.** Each extra turn adds delay, following Rubinstein's bargaining model; this is the argument for converging early.

Malformed output is re-prompted once, then sent to the fallback. A `stop_reason` of `refusal` or `max_tokens` also goes to the fallback.

## 4. Message contract (shared by every lane)

Implemented as Pydantic models and sent with JSON outputs (`client.messages.parse(output_format=...)`). Ranges are enforced in Python, because the schema format doesn't support min/max.

```json
{
  "agent": "ATC | PILOT | GROUND",
  "turn": 1,
  "type": "RANK | PROPOSE | CONCEDE | ACCEPT | REJECT",
  "option_ranking": ["opt_2", "opt_1"],
  "proposal": {"base_option": "opt_1", "changes": [{"flight": "UA123", "field": "slot|gate|hold_min|divert", "value": "..."}]},
  "concession": {"preference": "max_hold_min", "new_bound": 12},
  "accept_option": "opt_2",
  "objections": [{"option_id": "opt_1", "rule_ref": "C-FUEL-1", "evidence_ids": ["flt:UA123"]}],
  "rationale_short": "≤ 2 sentences"
}
```

Each consensus-log line contains: `ts, scenario_id, seed, turn, agent, message, checker_verdict, rule_ids, option_metrics, model, request_id, usage`.

## 5. Constraint checker rules

The data is US, but we encode the **ICAO** values and cite ICAO Doc 4444, because the FAA pages were blocked (403) and the heavy-aircraft pairs agree between ICAO and FAA anyway. Every simplification is labelled.

| ID | Rule | Value | Source |
|---|---|---|---|
| C-WAKE-1 | Arrival wake separation by leader→follower category | H→H 4 NM, H→M 5, H→L 6, M→L 5 (J→H 5, J→M 7, J→L 8) | ICAO Doc 4444 §8.7.3 via SKYbrary |
| C-SEP-1 | Minimum separation, no wake pair | 3 NM terminal (**assumption**; ICAO default is 5 NM). Converted to time at the approach speed | SKYbrary |
| C-RWY-1 | Arrivals on a closed runway or blocked taxiway | Forbidden | Scenario NOTAM |
| C-FUEL-1 | Holding may not eat into final reserve | Remaining fuel ≥ 30 min final reserve (ICAO). US 121.639 = 45 min, shown for reference | SKYbrary; 14 CFR 121.639 |
| C-FUEL-2 | Low-fuel flights get priority | Fuel margin < X min → cannot be resequenced later | Policy (assumption) |
| C-GATE-1 | No gate double-booking; size-compatible gate | Interval overlap = violation | Scenario |
| C-TURN-1 | Minimum turnaround before next leg | Narrow-body ≥ 25 min (P10 of scheduled) | Eurocontrol standard inputs |
| C-CREW-1 | Ground crew shift cap | 8 h shift + cap (**assumption**, no authoritative norm found) | Stated assumption |
| C-MCT-1 | Connection protected only if it meets the minimum connection time | Domestic 30–60 min, per airport | OAG (secondary) |

Holding fuel uses **25 kg/min for A320/737** (Airbus primary source). The dataset report's 2,300 kg/h (~38 kg/min) is the upper bound in the sensitivity check.

## 6. Data: real, enriched, synthetic

**Profile of the provided data** (stored at `data/raw/dot2015/`, gitignored, profiled 31 Oct):
- `flights.csv` has **358,774 rows and is pre-filtered.** Every row meets `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20` (42,012 weather, 326,249 late aircraft). There are **no on-time flights, no cancellations and no October.** The airport codes are IATA.
- Times are **zero-padded strings** (`"0648"`), so read them as strings, not integers.
- The densest disrupted arrival hours are almost all late-aircraft cascades: ATL 30 Dec 15:00 (58 delayed arrivals, mean 101 min), ATL 18 Jun 21:00 (49), DFW 13 Apr 17:00 (43, the most weather/carrier mix).
- **Consequence:** we cannot rebuild the *full* arrival bank. The scenario bank is the **delayed flights at that airport-hour** (real). Any on-time background traffic must be seeded synthetic and labelled. Tail rotations are partial (delayed legs only).
- `airports.csv` has 322 airports with lat/lon; `airlines.csv` has 14 carriers.


| Layer | Content | Provenance shown in UI |
|---|---|---|
| Real | The DOT 2015 row, **the other delayed arrivals at that destination airport in that hour ±1–2 h** (the file has no on-time flights), partial tail rotations, taxi-time distributions | `real` |
| Enriched | Aircraft type and wake category via the FAA registry (tail → MASTER → ACFTREF, plus a ~40-model hand map); runways from OurAirports; 2015 METARs from Iowa Environmental Mesonet | `enriched` (registry and runways are current, not 2015; match rate reported) |
| Synthetic (one logged `SEED`) | Gates, fuel on board (reserve + seeded 0–20 min), passenger connections (plausible same-airline links), crew rosters, METAR→capacity rule | `synthetic` |

Disruption mapping:
- **Weather delay:** METAR-based reduction in arrival capacity (e.g. 60 → 40 per hour), so the arrival bank must be resequenced or held.
- **Late aircraft:** the inbound arrives late, so a gate conflict and a squeezed turnaround hit the next leg.

Dataset quirks:
- **October airport codes are numeric**, so exclude October.
- Times are local hhmm with midnight wrap.
- Delay-cause columns are filled only when the arrival delay is at least 15 min.
- Load with `usecols`, and cache one airport-day to parquet.

## 7. Evaluation (the rubric's honest-evaluation criterion)

- **Scenarios:** {hub, medium airport} × {weather, late aircraft} × 8 = **N = 32**, fixed seed, 3 runs each. 8 held-out scenarios are never used for prompt tuning.
- **Baselines (same inputs):**
  - B0 do nothing (the delay cascades)
  - **B1 greedy first-come-first-served + wake separation + nearest free gate (= the fallback)**
  - B2 CP-SAT optimum (reference)
  - Single-prompt LLM, all three roles in one call (an ablation that shows *why* separate agents matter)
- **Metrics:**
  - Total, mean and P90 delay minutes
  - Holding fuel (kg) and CO₂ (×3.16)
  - Missed connections
  - Violations proposed, caught and **leaked (must be 0)**
  - Convergence within 3 turns and mean turns
  - Fallback rate
  - Tokens, USD and latency per negotiation
- **Reporting:** paired comparisons, bootstrap 95% CIs on delay differences, Wilson CIs on rates, "N = 32, indicative only", and a provenance table.
- **Ablation:** checker off. Count the unsafe acceptances the agents would have made, to show sycophancy (Yao 2025) and why the checker exists.

## 8. Failures to demo (at least one live)

These are tagged with MAST categories (Cemri 2025).
1. **The checker catches an unsafe agreement.** Agents converge on an option that breaks C-WAKE-1 or C-FUEL-1; it's vetoed with the rule ID and the fallback runs.
2. **Manipulation by framing** (NegotiationArena). The Pilot agent claims urgency without a matching fuel state; the outcome follows verified constraints only.
3. **Deadlock.** No agreement by turn 3, so the fallback decides; show the delay it cost compared with negotiated runs.
4. Also log: hallucinated gates or flights (caught by an ID check), hhmm arithmetic errors (impossible by design, since code does the time maths), malformed JSON, API timeout → fallback.

## 9. Claude implementation recipe

- Python `anthropic` SDK, `AsyncAnthropic`, and `asyncio.gather` for the 3 agents in each turn.
- **Models:** `claude-haiku-5-5` for development and evaluation (about $1.26 for 200 scenarios); `claude-sonnet-5-5` for the live demo (about $0.13 per run).
- **Structured output:** JSON outputs via `client.messages.parse(output_format=Model)`. **Don't force `tool_choice`**, since it returns a 400 on Sonnet/Opus 5.5.
- **Thinking:** adaptive by default. Set `output_config.effort` to `low` or `medium`. **Never send `budget_tokens`** (returns a 400). Use `display: "summarized"` to show reasoning summaries in the trace.
- **Caching:** system block 1 holds the shared scenario (`cache_control: ephemeral`), block 2 the role prompt. The prefix must be at least 512 tokens. Check `cache_read_input_tokens`. Keep `effort` and the schema fixed per run, because changing them invalidates the cache.
- **Evaluation runs:** `asyncio` + a semaphore (5–10 calls in flight). Batches are the production path; a negotiation needs 3 sequential batches, which is too slow for today.
- **Warm the schema up before the demo:** the first call compiles the grammar.
- Ask for a short rationale, not "step-by-step reasoning", which can trigger a refusal.
- Not used: Agent SDK, Managed Agents, Citations. They hide the orchestration, or conflict with JSON outputs.

## 10. Pitch spine (3 min)

1. **Hook (15 s).** "At $98 a minute, with airborne delay costing twice as much as gate delay, a duty manager spends the first hour of every storm on the phone."
2. **Demo (90 s).** A real 2015 disruption → three agents → a checker veto → agreement on turn 2 → plan and log.
3. **Evidence (35 s).** N = 32 results against greedy and CP-SAT, leaked violations = 0, fallback rate, and one failure shown.
4. **How it works (25 s).** The LLM-Modulo split: Claude negotiates, code verifies, and the duty manager decides.
5. **Next (15 s).** A-CDM milestone integration (TOBT/TSAT) and Skywise data.

## 11. Open risks and questions

- ~~Whether the organisers' DATA folder is the full 565 MB `flights.csv`~~ It isn't: it's a 38.6 MB pre-filtered subset (see §6). On-time background traffic is synthetic.
- Registry match rate for 2015 tails is unknown; fall back to a synthetic wake mix if it's low.
- C-SEP-1 (3 NM vs ICAO's 5 NM), C-FUEL-2 and C-CREW-1 values are assumptions. State them in the pitch.
- Whether greedy/CP-SAT options are good enough that the agents add value; if B2 always wins, the story becomes faster agreement plus trade-offs explained, not lower delay.

## Key citations
- Kambhampati et al. 2024, LLM-Modulo: https://arxiv.org/abs/2402.01817
- Ye et al. 2023, SatLM: https://arxiv.org/abs/2305.09656
- AhmadiTeshnizi et al. 2024, OptiMUS: https://arxiv.org/abs/2402.10172
- Abdelnabi et al. 2024, LLM-stakeholder negotiation: https://arxiv.org/abs/2309.17234
- Bianchi et al. 2024, NegotiationArena: https://arxiv.org/abs/2402.05863
- Fu et al. 2023, self-play negotiation: https://arxiv.org/abs/2305.10142
- Yao et al. 2025, sycophancy in multi-agent debate: https://arxiv.org/abs/2509.23055
- Cemri et al. 2025, MAST (why multi-agent systems fail): https://arxiv.org/abs/2503.13657
- Endriss 2006, monotonic concession protocols: https://eprints.illc.uva.nl/176/
- Vossen & Ball 2006, mediated bartering for Ground Delay Programs: https://ideas.repec.org/a/wly/navres/v53y2006i1p75-90.html
- Andriuškevičius & Sun 2024, LLM air traffic agents: https://arxiv.org/abs/2409.09717
- NASA Ames 2026, LLM human-machine teaming in ATM: https://ntrs.nasa.gov/citations/20250011241
- Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
