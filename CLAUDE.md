# Autonomous SG 2026 — team project

Six-hour hackathon build (Sat 31 Oct 2026). Goal: one agent that visibly completes a real, multi-step Singapore task end to end, with a human approval step and a tangible output (report, filled form, drafted email). Optimise for a working demo, not production quality.

## Problem
Airbus track, Challenge #2 (multi-agent disruption negotiation). **Read `docs/challenge-2-brief.md` (brief + rubric) and `docs/challenge-2-framing.md` (design) before building.**
User: airline OCC duty manager at a US hub. Three separate Claude agents (ATC, Pilot, Ground) negotiate over code-generated, code-checked recovery options for a real DOT 2015 disruption; ≤3 turns; deterministic fallback; JSONL consensus log. Claude negotiates and explains; code computes all numbers, checks every constraint and decides termination.

## Stack
TBD — chosen once the problem is picked. Candidates: Next.js + Vercel (TypeScript, `@anthropic-ai/sdk`, Stagehand/Playwright) or a Python backend (FastAPI, `anthropic`, Playwright/browser-use). Whichever we pick: a Claude tool-use loop with streaming, every step shown in the UI. Add run/build/deploy commands here once the app exists.

## Roles — one owner per folder, don't edit another person's folder
TBD — fill in names, lanes and folders once decided. Suggested lanes: agent loop and model routing; UI (live agent trace, approval step, output view); tools and data (browser automation, SG APIs, file/PDF output); evals, demo script and pitch.

## Contracts
Agent message schema, consensus-log line format and constraint rule IDs (C-WAKE-1, C-FUEL-1, …) are defined in `docs/challenge-2-framing.md` §4–5. Change them only there, in their own commit, and tell the team. Every lane builds against these.

## Models
- `claude-haiku-5-5`: bulk classify/extract/summarise (keep prompts under 100K tokens)
- `claude-sonnet-5-5`: main agent loop (default)
- `claude-opus-5-5`: one hard step only (planning, final grading, dense vision)
- Cache the system prompt and tool definitions (prompt caching)

## Rules
- Never commit keys. Real keys go in `.env.local` (gitignored); add new variable names to `.env.example`.
- Irreversible actions (send, submit, pay) must wait for the user's approval click.
- No Singpass, CAPTCHAs or logins in the demo path; seed demo data and cache flaky responses.
- Commit small, `git pull --rebase` before pushing, keep `main` deployable.
- Skip test-first TDD; verify the change actually works before saying it's done.

---

# CLAUDE.md — Airbus Challenge #2: Multi-agent disruption negotiation (MVP)

> Shared context for every Claude Code session on this team. Read fully before writing code.
> This is the AGREED scope. Do not build anything outside it without asking.
> Items marked **TODO** are filled in by the team.

---

## 1. Event & deadlines
- Autonomous SG 2026 (NUS) — AI & Aerospace track, Airbus Challenge #2.
- **Submissions close 16:15. Target submit: 15:45** (earlier submission scores higher).
- **Pitch: 3 minutes max.**

## 2. The challenge (essentials)
Multi-agent framework where **ATC, Pilot and Ground agents** negotiate a resolution to a disruption
until consensus. Must have: **structured messages, explicit constraint checking, traceable consensus
log, deterministic non-AI fallback**, resolution in **≤ 3 turns**.
**Must avoid:** combining roles in one prompt/call · unbounded agent loops · accepting plans that
ignore safety margins.

## 3. Rubric (optimise for this)
Technical soundness 25% (LLM for reasoning/explanation, code for constraints/scheduling; works beyond
the demo script) · Problem realism 20% · Honest evaluation 20% (baseline, metrics, visible failure) ·
Trust & traceability 20% (evidence visible, human decides) · Impact 10% · Time discipline 5%.

---

## 4. Scope (MVP — agreed)

### Events (only these two)
| Event | Trigger in DOT row | Effect on world state |
|---|---|---|
| **Weather** | `WEATHER_DELAY > 15` | Fewer arrival slots at destination (reduced capacity window) |
| **Late-arriving aircraft** | `LATE_AIRCRAFT_DELAY > 20` | Focal aircraft available late → gate & turnaround squeezed |

### Decisions (only these three)
| Decision | Options | Owner (proposes) |
|---|---|---|
| **Arrival time** | new arrival slot via **ground delay** (delay take-off) or **airborne holding** | ATC (Pilot accepts/counters) |
| **Gate** | keep gate & wait until free · change gate | Ground |
| **Flight plan** | continue · **divert** to alternate | Pilot |
| *(Cancellation)* | **recommendation to the human only — never an agent decision** | — |

### Flight state — ASSUMPTION (team to confirm)
- **MVP default: focal flight is pre-departure.** Pilot chooses between **accepting a ground delay**
  or **departing on time with extra holding fuel** (allowed only if planned holding ≤ extra fuel).
- **Stretch:** `airborne: true` scenarios (holding limited by fuel on board; diversion if exceeded).
- Code supports an `airborne` flag from the start so the stretch is a small change.

### Agents
- **3 agents per scenario:** ATC, Ground, and **one Pilot agent for the focal (disrupted) flight**.
- **Background flights** (same airport/hour from real data) are **passive**: they occupy slots/gates,
  the checker enforces their limits, and their knock-on delay is counted in cost. They do not negotiate.
- **ATC represents traffic flow / throughput** (including background flights' interests).

### Out of scope (pitch as "next steps")
Multiple Pilot agents · solver for whole traffic bank · runway closure / equipment / crew / security
events · live feeds · weather archives · aircraft registry · maps/Gantt visuals.

---

## 5. Workflow (the core design — follow exactly)

```
① EVENT (weather / late aircraft, from a DOT row)
      │ code: build_world(row, seed) → WorldState
      ▼
② PARALLEL ANALYSIS — ATC · Pilot · Ground (3 separate LLM calls, in parallel)
      each sees the event + ONLY its own facts → returns its preferred plan + needs
      ▼
③ NEGOTIATION — run by the MIDDLE MAN (pure code), max 3 rounds
      every plan → CONSTRAINT CHECKER (code) → valid? violations? cost?
      cheapest VALID plan goes on the table
      round 2–3: all 3 agents respond in parallel → accept / counter
        ├─ all 3 accept same plan_id → CONSENSUS
        └─ no consensus after round 3 → MIDDLE MAN HALTS → LEAST-COST VALID PLAN (fallback solver)
      ▼
④ DOCUMENT CRAFTER — LLM writes narrative ONLY from the structured log; code fills all numbers
      ▼
⑤ HUMAN (duty manager) → Approve / Reject (decision logged)
```

### Definition of a round
Round 1 = parallel proposals. Rounds 2–3 = parallel responses to the table plan.
**Max 3 rounds × 3 calls = ≤ 9 agent LLM calls per scenario** (+1 document call).

### Middle man (pure code — NOT an LLM)
```python
state  = build_world(row, seed)                                   # ①
plans  = parallel(agent.propose(state) for agent in AGENTS)       # ② round 1
table  = cheapest_valid(plans, state)                             # check + cost
for rnd in (2, 3):                                                # ③
    if table is None: break
    replies = parallel(agent.respond(table, check(table, state), log) for agent in AGENTS)
    log.add(rnd, table, replies)
    if all(r.action == "accept" for r in replies):
        return finish(table, log, outcome="consensus", rounds=rnd)
    counters = [r.plan for r in replies if r.action == "counter"]
    table = cheapest_valid(counters, state) or table
return finish(fallback(state), log, outcome="halt_least_cost")   # deterministic
```
- Invalid plans are **never shown to other agents**; the proposer sees the violations in the log.
- Invalid / unparseable agent output → re-ask once, then treat as `reject`.

---

## 6. World state (built by code, seeded per row)

| Field | Source | Real / derived / synthetic |
|---|---|---|
| Flight id, airline, tail, origin→dest, scheduled dep/arr, scheduled time, distance | DOT row | **Real** |
| Event type + magnitude | `WEATHER_DELAY` / `LATE_AIRCRAFT_DELAY` | **Real** |
| Background flights (slots/gates occupied) | Other DOT rows, same dest + date + hour | **Real** schedule |
| Focal aircraft's next departure | Same `TAIL_NUMBER` departing dest later that day | **Real** |
| Arrival slot grid (e.g. 5-min slots, reduced capacity in weather window) | Rule | Synthetic (labelled) |
| Gates (~4–6) + busy windows | Built from schedule + seeded | Synthetic (labelled) |
| Extra/holdable fuel | Formula below | **Derived** |
| Alternate airport | Nearest airport >100 nm from dest (airports.csv lat/long) | **Real coords**, rule |
| Crew shift end | Seeded (e.g. 8–10 h shifts) | Synthetic (labelled) |
| Connecting passengers | Seeded | Synthetic (labelled) |
| Weight class (separation) | By airline: MQ/EV/OO = regional, others = mainline | Synthetic rule (labelled) |

### Fuel (minutes, not kg)
```
reserve_min    = 45                                  # FAA 14 CFR 121.639
contingency    = max(5, 0.05 * SCHEDULED_TIME)        # ICAO-style 5%
discretionary  = seeded uniform(0, 20)                # synthetic
holdable_min   = contingency + discretionary          # holding allowed before touching alternate/reserve
```
Pre-departure: Pilot may request `extra_fuel_min` (costed) to depart on time and hold later.

### ⛔ No hindsight
Agents must never see outcome columns: `DEPARTURE_TIME`, `ARRIVAL_TIME`, `ARRIVAL_DELAY`,
`DEPARTURE_DELAY`, `WHEELS_ON/OFF`, `ELAPSED_TIME`, `AIR_TIME`, `TAXI_IN/OUT`.
These are used ONLY in evaluation as a historical reference.

---

## 7. Agents

Each agent = separate system prompt + separate call + **only its own facts** (via tools or injected
facts computed by code). Agents never do arithmetic or legality checks — code does.

| Agent | Sees | Objectives | Can offer |
|---|---|---|---|
| **ATC** | Slot grid, capacity window, background arrivals & weight classes, event | Throughput, separation, minimise total system delay | Re-sequence, different slot |
| **Pilot** (focal flight) | Airborne flag, holdable fuel, extra-fuel option, alternate, connections, weather on route | Safety/fuel margin, protect connections, minimise fuel burn, avoid turbulence | Accept ground delay, accept holding ≤ fuel, later slot, gate change if connections OK, **divert** (only Pilot can) |
| **Ground** | Gate timelines, crew shifts, turnaround times, focal aircraft's next departure | Gate utilisation, no crew overtime, protect turnaround | Gate change, wait for gate, shorter turnaround if crew allow |

**Pilot red line:** if fuel margin < 10 min → must flag `"MINIMUM_FUEL"`; ATC is told to prioritise.

### Message schema (every agent output)
```json
{
  "from": "atc | pilot | ground",
  "round": 1,
  "action": "propose | accept | counter | reject",
  "plan_id": "P3 (when accepting)",
  "plan": { "arrival_slot": "HH:MM", "ground_delay_min": 0, "holding_min": 0,
            "extra_fuel_min": 0, "gate": "C14", "divert": false },
  "need": "<= 20 words",
  "offer": "<= 20 words",
  "reason": "<= 30 words, cites a constraint or objective",
  "flags": ["MINIMUM_FUEL"]
}
```

### Agent independence — PROPOSED (`docs/agent-alignment.md`)
Agents share only the message (`action`, `plan_id`, `plan`, `reason`); constraints, interests, ranking and fallback are each agent's own.

---

## 8. Constraint checker (pure code → `{valid, violations[], checks[]}`)
Applies to the focal flight AND any background flight a plan moves.
1. **Fuel:** planned holding ≤ holdable fuel (+ extra fuel if loaded); margin reported
2. **Gate:** gate free for the full occupancy window (arrival → turnaround end)
3. **Slot:** slot free and within reduced capacity; spacing by weight class
4. **Crew:** ground crew shift end not exceeded (overtime → soft cost, flagged)
Hard violations → invalid. Soft costs → added to cost.

## 9. Cost model (pure code, fixed weights — all values in a config file, labelled)
| Item | Cost |
|---|---|
| Ground delay (per min) | lower (no fuel burn) |
| Airborne holding (per min) | higher — ref. ~$98/block-min (Airlines for America, 2025) |
| Extra fuel carried (per min loaded) | small |
| Gate change | fixed + connection risk |
| Waiting for occupied gate (per min) | like ground delay + pax-onboard penalty |
| Missed connection (per pax) | fixed |
| Crew overtime (per min) | fixed rate |
| Knock-on delay to background flights | same per-min rates |
| Diversion | large fixed |
| Cancellation (recommendation only) | largest, flagged to human |

**Primary metric: total system delay/cost** (focal + knock-on) — prevents pushing delay onto others.

## 10. Fallback solver (pure code, deterministic)
Enumerate all slot × gate × {ground delay | holding w/ extra fuel} × {continue | divert} options
(~tens of combos), drop invalid ones, return the cheapest. If none valid → recommend cancellation
to the human. **This is also the evaluation baseline.**

## 11. Consensus log (traceability)
Every entry: `timestamp, round, agent, message JSON, checker result, cost, table_plan_id`.
Shown live in the UI; exported as JSON with each decision document.

## 12. Document crafter
- **Input: the structured log only.** Code fills a template with all numbers; the LLM writes only
  the plain-English explanation and must not introduce facts not in the log.
- Document sections: **Decision** · **How reached** (consensus in round N / ⚠️ halt + least-cost) ·
  **Why** (each agent's key reason, quoted) · **Safety checks** (fuel/gate/slot/crew with values) ·
  **Cost** (total, knock-on, vs alternatives) · **Assumptions** (synthetic inputs listed) ·
  **Uncertainty** (e.g. thin fuel margin) · **[Approve] [Reject]** (human choice logged).

---

## 13. Evaluation (honest evaluation = 20%)
Batch-run ~30 rows (mix of weather and late-aircraft). Report agents vs fallback baseline:
- % consensus within 3 rounds
- **Hard-constraint violations (must be 0)**
- Avg total system delay & cost; focal delay; knock-on flights affected
- Avg rounds, LLM calls, latency per scenario
- Historical reference: actual 2015 `ARRIVAL_DELAY` (caveat: different assumptions)
- **Show at least one failure** (no consensus → halt, or agents worse than fallback) and explain why.
- Cache LLM responses by (model, prompt) so re-runs are free and reproducible.

**Demo scenario:** DFW, 24 Apr 2015 (real weather cluster: 79 weather-delayed arrivals that day).

---

## 14. Models
- Agents: Sonnet tier. Document crafter: Sonnet tier. (Haiku only if latency/cost forces it.)
- Confirm exact model IDs with the `claude-api` skill. Set `max_tokens` on every call.

## 15. Stack & layout — TODO (team lead)
- Stack: _fill in_
- Suggested modules: `world.py` (build_world) · `checker.py` · `cost.py` · `fallback.py` ·
  `agents/` (prompts + agent.py) · `middleman.py` · `document.py` · `evaluate.py` · `ui/`
- `.env.example` lists keys; never commit real keys. Client SDK + our own loop; no agent frameworks.

## 16. Roles
- **A:** agent prompts + agent.py + middleman loop
- **B:** world builder + checker + cost + fallback (+ unit tests)
- **C:** UI (event → live log → document → approve/reject)
- **D:** evaluate.py + results table + failure case + README (assumptions) + pitch

## 17. Timeline (from 13:20)
| Time | Goal | Check |
|---|---|---|
| 13:20–14:30 | B: world/checker/cost/fallback · A: prompts + middleman | One row → plan + log in terminal |
| 14:30–15:00 | C: UI wired · D: eval on 30 rows · document crafter | **15:00 FEATURE FREEZE** |
| 15:00–15:30 | Results table, failure case, README, demo runs 3× clean | — |
| 15:30–15:45 | Rehearse 3-min pitch, **SUBMIT** | ✅ |

## 18. How Claude should work here
- Never put arithmetic, scheduling or legality checks in a prompt — write code.
- Never merge agent roles; one call per agent per round.
- Simplest end-to-end first (terminal), then UI.
- Log every LLM call during development.
- If something in this file is ambiguous enough to change the design, **ask before building**.
- Ask before adding dependencies or external services.
