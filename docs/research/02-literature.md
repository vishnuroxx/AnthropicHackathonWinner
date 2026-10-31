# Research: literature on agentic / multi-agent systems (Challenge #2)

Research-agent report, 31 Oct 2026. Most citations checked by web search; **[unchecked]** = cited from memory.

## Amendments: what changed and why
The literature findings themselves are unchanged. Two items in the synthesised architecture below were adjusted once the provided data and hackathon constraints were known:

| # | Previously proposed | Amended to | Why |
|---|---|---|---|
| L1 | Item 4: the option set includes runway slot, stand, holding **and diversion** | Option set = **runway slot / resequence, holding minutes, gate (re)assignment**. No diversion or cancellation | The provided data has no diverted or cancelled flights, so those actions can't be grounded or evaluated (`04-data-and-evaluation.md` A7) |
| L2 | Item 10: evaluate on "~20 scenarios with renamed entities" | Evaluate on **N = 32 stratified scenarios** (airport tier × cause) as in `04` §5. Renaming entities is kept as an optional robustness check | Aligns the two reports on one evaluation plan. Renaming tests memorisation (Abdelnabi et al.) but isn't essential with 6 hours |

## 1. LLM + external verifier / solver
- **Kambhampati et al., 2024 — "LLMs Can't Plan, But Can Help Planning in LLM-Modulo Frameworks" (ICML 2024).** https://arxiv.org/abs/2402.01817 — LLMs generate candidates; sound external critics verify; bounded feedback loop. Position paper. **Use:** backbone citation — Claude proposes/explains, deterministic critics check separation, slots, crew, turnaround; only critic-approved options can be accepted.
- **Ye, Chen, Dillig, Durrett, 2023 — "SatLM" (NeurIPS 2023).** https://arxiv.org/abs/2305.09656 — LLM writes declarative spec, solver solves; beats program-writing; solver can report UNSAT. **Use:** agents emit typed constraints/preferences, never computed times; UNSAT reasons fed back.
- **AhmadiTeshnizi, Gao, Udell, 2024 — "OptiMUS" (ICML 2024).** https://arxiv.org/abs/2402.10172 — LLM writes MILP for a solver; large gains over prompting. **Use:** justifies CP-SAT for runway/stand re-sequencing; LLM only sets weights/priorities.

## 2. LLM negotiation and coordination
- **Abdelnabi et al., 2024 — "Cooperation, Competition, and Maliciousness: LLM-Stakeholders Interactive Negotiation" (NeurIPS 2024 D&B).** https://arxiv.org/abs/2309.17234 — multi-party multi-issue games; strong models often fail to agree in harder games. **Use:** private per-issue scores + minimum acceptable score per agent; agreement = everyone ≥ minimum.
- **Bianchi et al., 2024 — "How Well Can LLMs Negotiate? NegotiationArena" (ICML 2024).** https://arxiv.org/abs/2402.05863 — LLMs irrational and manipulable ("desperate" framing +~20% payoff). **Use:** urgency framing must not change verified constraints; adversarial test.
- **Fu, Peng, Khot, Lapata, 2023 — self-play negotiation.** https://arxiv.org/abs/2305.10142 — more critic rounds help but raise deal-breaking. **Use:** supports the hard 3-turn limit.
- **Du et al., 2023 — Multiagent Debate.** https://arxiv.org/abs/2305.14325 [unchecked] — background; gains since disputed.
- **Yao et al., 2025 — "Peacemaker or Troublemaker: How Sycophancy Shapes Multi-Agent Debate".** https://arxiv.org/abs/2509.23055 — sycophancy → premature consensus. Related: CONSENSAGENT (ACL Findings 2025); "The Cost of Consensus" https://arxiv.org/abs/2605.00914. **Use:** agreement ≠ evidence; measure infeasible acceptances with the gate off.
- **Cemri et al., 2025 — "Why Do Multi-Agent LLM Systems Fail?" (MAST, NeurIPS 2025 D&B).** https://arxiv.org/abs/2503.13657 — 14 failure modes; most from system design. **Use:** tag our failure cases with MAST categories.

## 3. Classical protocols with termination guarantees
- **Smith, 1980 — Contract Net Protocol** [unchecked]. **Use:** T1 mediator announces disruption, agents bid options.
- **Rubinstein, 1982 — alternating-offers bargaining** [unchecked]. **Use:** per-turn delay cost pushes early concession.
- **Rosenschein & Zlotkin, 1994** [unchecked]; **Endriss, 2006 — "Monotonic Concession Protocols for Multilateral Negotiation" (AAMAS).** https://eprints.illc.uva.nl/176/ — concede-or-stop guarantees termination. **Use:** the convergence argument; non-concession = final reject; turn 3 forces fallback.
- **Vossen & Ball, 2006 — mediated bartering for Ground Delay Programs.** https://ideas.repec.org/a/wly/navres/v53y2006i1p75-90.html — FAA CDM uses a central mediator + optimisation (Ration-by-Schedule, Compression). **Use:** aviation precedent for a deterministic mediator; RBS + Compression as fallback/baseline.
- **Modi et al., 2005 — ADOPT (DCOP)** [unchecked] — formal framing only; don't implement.

## 4. LLMs in ATM / airports
- **Andriuškevičius & Sun (TU Delft), 2024 — "Automatic Control With Human-Like Reasoning: Exploring Language Model Embodied Air Traffic Agents".** https://arxiv.org/abs/2409.09717 — function-calling LLM agents in BlueSky solved 119/120 conflict scenarios. Closest prior work.
- **NASA Ames, 2026 (AIAA SciTech) — "Towards Naturalistic Human-Machine Teaming With LLM Agents: A Case Study in ATM".** https://ntrs.nasa.gov/citations/20250011241 — role-specialised LLM agents in BlueSky as decision support (abstract only).
- **ChatATC, EPFL TRC-30 (2024).** https://trc-30.epfl.ch/wp-content/uploads/2024/09/TRC-30_paper_137.pdf — human keeps final decision.
- **SESAR SIDs 2024 paper 047.** https://sesarju.eu/sites/default/files/documents/sid/2024/papers/SIDs_2024_paper_047%20final.pdf [abstract only]
- **ICAO APAC DGCA60, 2025 — A-CDM to TAM transformation in China.** (ICAO APAC 60-DP-04-06) — Shanghai Pudong deploying LLM agents on top of A-CDM (Jan 2025). A-CDM milestones (TOBT, TSAT) → message fields. No peer-reviewed paper found on LLM agents for A-CDM → our build is novel there.

## 5. Practitioner guidance
- **Anthropic, Dec 2024 — "Building Effective Agents".** https://www.anthropic.com/research/building-effective-agents [unchecked] — prefer simple workflows; orchestrator-workers, evaluator-optimizer.
- **Anthropic, Jun 2025 — "How we built our multi-agent research system".** https://www.anthropic.com/engineering/multi-agent-research-system — multi-agent +90.2% on internal eval, ~15× tokens; private contexts; prompt design is the main lever.

## Synthesised architecture
1. Deterministic Python mediator owns the protocol (turns, termination).
2. Three separate Claude agents with private constraints and utility weights; never see each other's private state.
3. Typed messages via tool use: `PROPOSE{option_id, rationale}`, `ACCEPT{option_id}`, `REJECT{option_id, violated_constraint_ids, counter}`, `CONCEDE{issue, new_bound}`; malformed → re-prompt once.
4. Solver/rule code generates the feasible option set with computed delays/costs; LLMs choose and argue, never compute times.
5. Verifier gate (LLM-Modulo critics): separation, fuel/holding endurance, crew duty, turnaround. Failing ACCEPTs are overridden and logged.
6. Monotonic concession, hard 3-turn limit: T1 bids, T2 must concede, T3 final accept/reject; delay cost rises per turn.
7. Agreement rule in code: among options all accepted and gate-passing, maximise min utility (or Nash product).
8. Deterministic fallback on no consensus / API failure: RBS / FCFS + priority (emergency > low fuel > connections); doubles as baseline.
9. Append-only JSONL consensus log rendered as a timeline.
10. Eval: LLM negotiation vs fallback vs single-prompt baseline on ~20 renamed scenarios; violations caught, consensus rate, turns, delay vs solver optimum, MAST-tagged failures.

## Failure modes to demo and measure
1. **Sycophantic early agreement** — gate off: count unsafe acceptances; gate on: show blocks.
2. **Manipulation by framing** — Pilot fakes urgency without matching fuel state; outcome must follow verified constraints only.
3. **Non-convergence / broken deals** — show the 3-turn limit firing the fallback; report fallback rate and delay cost.
