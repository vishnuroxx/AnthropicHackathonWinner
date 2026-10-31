# Challenge #2 — brief and judging rubric (source of truth)

Transcribed from `Autonomous SG 2026_Airbus Track.pdf` (AI & Aerospace track, Airbus). Read this before designing or building anything.

## Brief

**"How might AI help air traffic controllers, pilots and ground operations staff make faster and better decisions?"**

**Description.** Today, when a runway closes, weather delays occur or ground equipment fails unexpectedly, communications rely on human phone calls, manual software updates etc., leading to cascading delays, excessive holding patterns, and excessive fuel consumption. The future of Air Traffic Management relies on AI assistants that can autonomously communicate and negotiate trade-offs across organisational boundaries.

**Want to see.** A Multi-Agent Communication Framework where ATC AI agents, Pilot AI agents, and ground ops agents negotiate resolutions to real-time disruptions without human intervention until a consensus is reached.

| Agent | Must take care of |
|---|---|
| ATC | Runway wake separation, taxiway blockage, maximise sector throughput |
| Pilot | Preserve fuel reserves, ensure flight safety, minimise turbulence, protect passengers' connections |
| Ground | Optimise gate utilisation, avoid ground-crew overtime, minimise turnaround delays |

The 3 agents must exchange structured data, evaluate cross-domain constraints, and converge on an agreed solution. Required: **structured messages, explicit constraint checking, traceable consensus log, deterministic non-AI fallback.** Demonstrate agents negotiating a **revised arrival time, gate assignment, or flight plan adjustment in under 3 turns.**

**What to avoid**
- Combining the 3 roles into a single prompt call — the point is multi-agent coordination across independent domains.
- LLM agents talking in endless, unconstrained loops with no convergence logic / turn limits.
- Disregarding safety margins — agents must not accept solutions that ignore operational constraints.

**Provided data.** US DOT 2015 flight delays and cancellations (dataset folder `Challenge #2\DATA` in the organisers' Drive). Pick any row with `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20` and pass that row's parameters into the 3 agents.

## Judging rubric (Airbus track) — weighted, each criterion 1–5

| Criterion | Weight | Strong | Weak |
|---|---|---|---|
| Problem realism | 20% | Named user, narrow workflow, clear status quo and cost | Generic aviation chatbot |
| Technical soundness | 25% | Works end to end; LLMs for reading/explanation, **solvers/rules/statistics for scheduling, constraints, detection**; tested beyond a script | LLM-only legality checks, opaque scores, hard-coded demo |
| Honest evaluation | 20% | Baseline, measured results, labelled synthetic data, **a visible failure with a reason** | Only success cases, unsupported claims |
| Trust and traceability | 20% | Claims trace to a document/rule/timestamped signal; uncertainty visible; qualified person in control | Confident unsourced answers, claims to replace experts |
| Impact | 10% | Credible before/after vs baseline (e.g. delay minutes) | Big claims, no baseline |
| Time discipline | 5% | Early submission, focused pitch under 3 minutes | Late, rushed, over time |

Judges' notes: "Where does this fail, and how would your user know?" — "Reward sound restraint, not presentation polish." 3 judges per project.
