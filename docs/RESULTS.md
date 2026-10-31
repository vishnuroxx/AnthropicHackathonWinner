# Evaluation results: does the system do what the brief asks, and what does it save?

Generated 2026-11-01 00:26 by `.venv/bin/python -m evaluation.evaluate` (sample seed 2015, world seed 7). Raw data: `results/evaluation/summary.json`, `results/evaluation/rows.jsonl`, one consensus log per scenario in `results/evaluation/logs/`.

**Sample:** N = 32 real DOT 2015 rows, {large, medium hub} x {weather, late aircraft} x 8, fixed seed, October excluded, plus the DFW 24 Apr 2015 demo row reported separately. Cost and delay are compared on the 31 scenarios where the system produced a plan; 1 scenario ended in a cancellation recommendation and is discussed as a failure. **Indicative only:** synthetic gates, crews, connections and filler traffic (labelled in each lane).

**Mode:** dry run. Rounds 1-2 are each lane's code-side ranking; round-3 votes are the lanes' dry-run policies. No LLM calls are made, so the run is free and reproducible. Live Claude votes: `--live N` (needs ANTHROPIC_API_KEY); not run for this file.

## Headline

| | Status quo (B0) | **Negotiated system** | Fallback solver (B1) |
|---|---|---|---|
| Total cost, 31 scenarios (shipped cost model) | $69,568 | **$28,002** | $27,296 |
| Total cost incl. missed connections from late arrival | $124,968 | **$87,402** | $86,696 |
| Plans breaking a hard rule | 6 | **0** | 0 |
| Passenger minutes waiting onboard for a gate | 653 | **8** | 8 |
| Mean focal delay (min) | 44.0 | **50.7** | 51.3 |
| Airborne holding (min) / CO2 (kg) | 0 / 0 | **0 / 0** | 0 / 0 |
| Missed connecting pax (Pilot's count) | 277 | **297** | 297 |

- **Cost:** the system saves **$41,566** across 31 disruptions ($1,341 per disruption, 60% of status-quo cost). With missed connections priced in, the saving is $37,566. Paired per scenario: cheaper in 23, tied in 8, dearer in 0; mean difference -$1,341, bootstrap 95% CI [-$1,874, -$864].
- **Safety:** 0 hard-rule violations reached the duty manager. The status quo breaks a hard rule in 6 of 31 scenarios, every time by leaving passengers waiting more than 30 min for an occupied gate. The checker removed 139 of 604 proposed plans.
- **Price paid:** the system accepts **+6.6 min** more mean system delay than the status quo (95% CI [3.2, 10.4] min). It trades minutes for not keeping passengers onboard at a blocked gate, which costs more per minute.
- **Negotiation vs solver:** the negotiated plan equals the least-cost solver's plan in 29 of 31 scenarios. In the dry run, the money is saved by the shared checker and cost model, not by the negotiation itself (see §4).

## 1. Does it do what the brief and CLAUDE.md require?

| Requirement (source) | Status | Evidence |
|---|---|---|
| 3 separate agents, one call each, never one prompt (brief: avoid) | Met | `mediator/adapters.py` LaneAgent per lane; live mode = 3 separate Claude calls in round 3 |
| Structured messages (brief) | Met | `mediator/core.py` ScoredPlan / Vote; lane schemas in `agents/schema.py` |
| Explicit constraint checking in code (brief, rubric 25%) | Met | `check_plan`: C-CAP-1, C-FUEL-1, C-CREW-2, C-GATE-1/2, C-TURN-1; 139 unsafe plans caught |
| Traceable consensus log (brief) | Met | JSONL per run + plain-English decision record (`mediator/report.py`) |
| Deterministic non-AI fallback (brief) | Met | `fallback/scenario.py`; ran in 11 of 32 scenarios |
| Resolve in under 3 turns, no unbounded loop (brief) | Met | fixed 3 rounds, max 3; mean 0.81 s per scenario (dry) |
| Never accept unsafe plans (brief) | Met | 0 leaked; final check before output |
| Human decides (rubric: trust) | Mostly | Approve / Reject buttons in `app_prime.py` and `app.py`; the choice is kept in the UI session, not yet written to the consensus log |
| Baseline + metrics + visible failure (CLAUDE.md §13) | **Was missing, now added** | this file, `evaluation/` |
| Weather = fewer arrival slots (CLAUDE.md §4) | **Weak** | 7 of 8 medium-hub weather rows produce zero delay under every method (actual 2015 mean 138.2 min), see §5 |
| Depart on time + hold with extra fuel (CLAUDE.md §4) | **Broken** | 468 of 580 hold options fail the Pilot's fuel check as shipped; 0 would fail with extra fuel sized to the Pilot's holdable fuel, see §5 |
| Document crafter (LLM narrative from log, CLAUDE.md §12) | Not built | `mediator/report.py` is a code template; good enough for traceability |

## 2. Cost improvement: every method on the same scenarios

All methods use the same scenario, the same checker (`mediator.adapters.check_plan`) and the same cost model (`plan_cost`: ATC delay/holding/knock-on + Ground gate/crew/connection). *Connection-aware* adds $200 for each passenger the Pilot lane counts as missing a connection because of the arrival time, which `plan_cost` leaves out (§5).

| Method | What it does | Rule breaks | Mean cost | Mean conn.-aware cost | Mean focal delay | Mean system delay | Gate wait (min) | Gate changes |
|---|---|---|---|---|---|---|---|---|
| B0 | Status quo: FCFS ground delay, keep gate | 6 | $2,244 | $4,031 | 44.0 | 44.7 | 653 | 0 |
| B0h | Status quo: depart on time, hold in air | 6 | $2,258 | $4,045 | 44.0 | 44.7 | 653 | 0 |
| atc_alone | ATC decides alone | 2 | $1,307 | $3,094 | 44.6 | 44.7 | 324 | 13 |
| pilot_alone | Pilot decides alone | 2 | $1,335 | $3,122 | 44.0 | 44.7 | 324 | 13 |
| ground_alone | Ground decides alone | 1 | $958 | $2,874 | 50.9 | 51.6 | 8 | 15 |
| NEG | Negotiated (3 agents + mediator) | 0 | $903 | $2,819 | 50.7 | 51.3 | 8 | 15 |
| B1 | Fallback least-cost solver | 0 | $881 | $2,797 | 51.3 | 51.4 | 8 | 15 |

By scenario type (mean connection-aware cost):

| Stratum | n | Consensus | Status quo | System | Solver | Mean system focal delay | Actual 2015 delay |
|---|---|---|---|---|---|---|---|
| large/late_aircraft | 8 | 8/8 | $8,060 | $6,318 | $6,318 | 78.5 | 92.6 |
| large/weather | 7 | 5/8 | $4,516 | $1,026 | $932 | 7.9 | 43.4 |
| medium/late_aircraft | 8 | 0/8 | $3,573 | $3,673 | $3,673 | 111.0 | 112.1 |
| medium/weather | 8 | 8/8 | $37 | $37 | $31 | 0.2 | 138.2 |

Actual 2015 arrival delay (evaluation only, never shown to agents): mean 102.9 min over 32 rows. The real delay includes every cause and a full day's knock-on, so it's context, not a like-for-like baseline.

## 3. How each decision changed the system

Savings vs the status quo, split by decision. The gate decision is priced alone (status-quo slot with the system's gate); the slot/lever decision is the remainder. Same cost model throughout.

| Decision | Owner | Saving | Scenarios it helped | Scenarios it cost |
|---|---|---|---|---|
| Gate: move off an occupied gate instead of waiting with pax onboard | Ground | $40,303 | 15 | 0 |
| Arrival slot / lever: ground delay, retime to cut knock-on or gate wait | ATC + Pilot | $1,263 | 9 | 2 |
| **Total** | | **$41,566** | | |

Other design decisions, measured:

- **Code checker before anything is shown or picked.** It caught 139 unsafe proposals. Each agent's own favourite plan was unsafe in ATC 3, PILOT 3, GROUND 1 scenarios. With the checker off, the mediator's pick would itself be unsafe in 1 scenario(s). The agents' own vetoes catch most cases, but not all.
- **Multi-agent instead of one domain deciding alone.** Ground alone costs $958 per disruption and breaks a hard rule in 1 scenario(s). ATC alone ($1,307) and Pilot alone ($1,335) cost more than the system ($903) and break hard rules in 2 and 2 scenarios (they leave the flight at a blocked gate), which the system never does (0).
- **Ground delay instead of airborne holding.** The system planned 0 min of holding (0 kg CO2), against 9 min (1,137 kg) for depart-on-time-and-hold. Ground delay is half the cost per minute ($49 vs $98/min) and burns no fuel.
- **Nash-product pick protects the Pilot's interests (demo row DFW-20150424-MQ3086).** The least-cost solver picks 21:52 at gate A12 ($10,804, 287 pax miss connections). The negotiated plan is 21:09 at gate B20 ($11,915, 191 pax miss). It is $1,110 dearer on the shipped cost but **$18,090 cheaper** once missed connections are priced. Against the status quo ($58,528, gate wait 108 min, rule broken) it saves $8,412. Status-quo airborne holding on this row would break the fuel rule and force a diversion ($97,423).

## 4. What the negotiation adds, honestly

- Consensus in 21 of 32 scenarios (66%, Wilson 95% CI 48%-80%). Outcomes: {'consensus': 21, 'no_consensus': 10, 'no_valid_plan': 1}. The fallback ran in the rest.
- No-consensus causes: *atc rejected: Own option O1 has lower total_system_delay_min (n) than the table* (10 scenarios). ATC's round-3 dry-run policy rejects any plan whose system delay is above its own best option. The mediator picks on the product of all three scores and cost, so ATC's vote rule and the pick rule disagree by design. The fallback then picks the same plan the mediator had already picked.
- The negotiated plan equals the least-cost solver's in 29 of 31 scenarios. The pitch claim should be *'agents agree on a near-least-cost plan and explain it; code guarantees safety'*, not *'negotiation beats the optimiser'*.

## 5. Failures and bugs found (with the owner's folder)

1. **Cost model ignores delay-caused missed connections** (`mediator/adapters.py: plan_cost`). Ground only prices a missed connection when a gate change adds a long walk; the Pilot's count of passengers missing onward flights because of a late arrival is never priced. So the system will add delay to save a little gate-wait cost even when passengers then miss connections. Example: PHX-20150803-AA703 adds 20 min to save $400, and 20 pax miss connections (connection-aware: $2,314 -> $5,914). *Fix:* add `assess_plan(...).pax_missed * MISSED_CONNECTION_PER_PAX` to `plan_cost`.
2. **Extra holding fuel is sized against the wrong number** (`atc-agent/atc_agent/menu.py`: `extra = max(0, hold - HOLDABLE_MIN)` with `HOLDABLE_MIN = 45`). The Pilot can hold only 45 min spare minus the time to the alternate before the must-divert point (18.3 min at DFW). 468 of 580 hold options fail C-FUEL-1, so 'depart on time and hold' is never available. *Fix:* size extra fuel from the Pilot's `holdable_before_divert_min`.
3. **Weather barely disrupts anything at medium hubs** (`atc-agent/atc_agent/world_stub.py: weather_hours`). Capacity is cut only in hours with a cluster of weather-delayed arrivals. 7 of 8 medium-hub weather rows produce zero delay and $0 cost, while the row itself reports a weather delay. *Fix:* always cut capacity in the focal hour when `WEATHER_DELAY > 15`, or start the focal flight at `sched + WEATHER_DELAY` as late-aircraft does.
4. **False 'no valid plan' from a cross-lane mismatch** (DFW-20150303-MQ3275). Ground's world (`ground_agent/inputs.py`) treats the weather delay as a late arrival, so it sets 'now' (when Ground hears of the disruption) to 60 min before `sched + WEATHER_DELAY`. ATC lands the flight near its scheduled time, so every gate change fails C-GATE-2 with negative notice, the scheduled gate is busy, and the system recommends cancellation. The behaviour is safe (the human is told, nothing is auto-applied), but the cause is a bug, not an operational fact. *Fix:* one shared `disrupted_arrival` for all lanes. The ATC menu horizon (90 min) is also too short for a 185-min weather event.
5. **No-consensus by rule mismatch** (§4, `atc-agent/atc_agent/agent.py` dry-run policy). All 8 medium-hub late-aircraft rows fail to reach consensus.
6. **Implausible connection counts** (`agents/pilot_inputs.py: derive_connections`). Every same-airline departure 35-180 min later gets 3-25 connecting pax, so the demo's ~50-seat MQ regional jet reports 191+ missed connections. *Fix:* cap the total at a share of seats for the aircraft class.
7. **The gate saving is partly built into the synthetic world.** `ground_agent/inputs.py` always books the scheduled gate A12 until after the disrupted arrival, so the status quo always faces a gate conflict. That's realistic for a late-aircraft cascade, but the size of the gate saving depends on a synthetic choice. Say so in the pitch.

## Caveats

- N = 32 with one world seed: indicative only. The CIs cover sampling across rows only, not uncertainty in the synthetic inputs or cost weights; a second world seed and a weight sensitivity sweep are the next checks.
- Status quo B0 is our model of today's process: FAA-style first-come-first-served ground delay and keep the scheduled gate. It's priced by the same model, not observed.
- Synthetic and labelled: filler arrivals, gate occupancy, crew report and shift times, connecting pax counts. Workbook limits come from `data/raw/challenge2/challenge-2-operational-constraints.xlsx`.
