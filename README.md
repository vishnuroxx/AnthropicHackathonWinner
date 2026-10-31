# Multi-agent disruption negotiation — Airbus Challenge #2 (Autonomous SG 2026)

Three independent Claude agents (ATC, Pilot, Ground) negotiate a recovery plan for a real DOT 2015
disruption (weather or late aircraft) in ≤ 3 rounds. Code computes every number and checks every
constraint; a deterministic fallback decides if there's no consensus; a human duty manager approves.

## Run
```bash
.venv/bin/python -m mediator.run            # dry run, no LLM calls (DFW, 24 Apr 2015, MQ3086)
.venv/bin/python -m mediator.run --live     # Claude agents vote (needs ANTHROPIC_API_KEY in .env.local)
.venv/bin/python -m fallback                # deterministic least-cost fallback (baseline)
```
Output: a JSONL consensus log and a plain-English decision record in `logs/`.

## Layout
- `atc-agent/` ATC: arrival slot, wake separation, hourly capacity, background flights
- `agents/` Pilot: fuel reserve, divert point, crew duty, connections
- `ground_agent/` Ground: gate, turnaround, ground crew
- `mediator/` 3-round negotiation, constraint checks, log, decision record
- `fallback/` deterministic rules-based solver (also the evaluation baseline)
- `docs/` brief, design, agent agreement

## Data and assumptions
Real: DOT 2015 `flights.csv` row (schedule, event magnitude). Limits: organiser workbook
`data/raw/challenge2/challenge-2-operational-constraints.xlsx`. Synthetic and labelled: gate occupancy,
filler arrivals, connecting passengers, crew report times. No outcome columns reach the agents.
