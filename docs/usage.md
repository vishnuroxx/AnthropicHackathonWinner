# Using the duty manager console

For the person who owns the recovery decision: an airline operations centre duty manager. The console shows a real delayed flight, lets three agents (ATC, Pilot, Ground) settle on a plan in at most three rounds, and leaves the final call to you.

## Start it

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app_prime.py
```

Open the address it prints (usually http://localhost:8501). `app.py` is an alternative layout over the same engine.

## Run a disruption

1. **Pick a flight** in the sidebar under **Disrupted flight**.
2. **Leave "Replay saved run" on** for an instant, repeatable replay. Turn it off to have the three Claude agents vote live; this needs `ANTHROPIC_API_KEY` in `.env.local` and the result may differ from the saved run.
3. Read **What happened** (the real 2015 flight) and open **Limits we have to respect** to see the fuel, gate, capacity and crew limits. Each limit is tagged *real rule* or *simulated*.
4. Click **Find a recovery plan**. The progress bar walks through the five stages:

   | Stage | What happens |
   |---|---|
   | 1. Disruption | A delayed flight comes in |
   | 2. Each team weighs in | ATC, Pilot and Ground each suggest plans |
   | 3. Agree on a plan | Unsafe plans removed; settle in 3 rounds or less |
   | 4. Recommendation | A plain-English summary of what and why |
   | 5. Your call | You approve or reject |

5. Read the **Recommended plan** and decide: **Approve plan** or **Reject plan**.

## What the outcome means

| You see | Meaning | What to do |
|---|---|---|
| The teams agreed | All three agents accepted the plan and it passed the final safety check | Check the plan and the reasons, then decide |
| "The teams did not agree, so the system picked the cheapest safe plan automatically." | At least one agent rejected; the non-AI fallback chose the cheapest plan that passes every safety rule | Read the rejection reason before approving: the fallback does not take it into account |
| Cancellation recommended | No plan passed every safety rule | Nothing is applied. Confirm the cancellation or handle it manually |

Every plan shown has passed all hard safety rules (fuel, crew duty, runway capacity, wake separation, gate availability). Turn on **Show the technical decision record** to see every proposal, every rule that removed a plan, every score and every vote.

## Demo flights

| Flight | Date (2015) | Event | Expected outcome (saved run) |
|---|---|---|---|
| AA36 SAN→DFW | 24 Apr | Weather, 47 min | Consensus |
| AA96 STL→DFW | 24 Apr | Late aircraft, 62 min | Consensus |
| OO6213 CVG→ORD | 3 Aug | Weather, 72 min | No consensus: ATC rejects; fallback picks 08:40 arrival, 35 min ground delay, gate B20 |
| AA1480 MCI→DFW | 24 Apr | Weather | Cancellation recommended |
| AA98 MSY→DFW | 24 Apr | Late aircraft, 90 min | Cancellation recommended |

## Good to know

- **Simulated inputs are labelled.** Gate occupancy, other airlines' filler traffic, connecting passenger counts and crew times are synthetic; flight schedules and delay causes are real.
- **Your approval isn't saved yet.** Approve / Reject is held for the current session only; it is not written to the consensus log.
- **The cost doesn't yet count passengers who miss connections because the flight lands late.** The Pilot agent reports them in its reason; weigh them yourself.
- **Live runs can differ from saved runs**, because the agents' round-3 votes come from Claude.

More limits and their causes: [RESULTS.md §5](RESULTS.md).

## Command line

```bash
.venv/bin/python -m mediator.run                         # one negotiation, no LLM (DFW, 24 Apr 2015, MQ3086)
.venv/bin/python -m mediator.run --date 2015-08-03 --dest ORD --flight OO6213
.venv/bin/python -m mediator.run --live                  # round-3 votes by Claude
.venv/bin/python -m evaluation.evaluate                  # 32-row evaluation -> docs/RESULTS.md
```

Each run writes a JSONL consensus log and a plain-English decision record to `logs/`.
