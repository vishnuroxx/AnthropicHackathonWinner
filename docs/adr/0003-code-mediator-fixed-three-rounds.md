# ADR-0003: A pure-code mediator runs exactly three rounds

**Status:** Accepted.

## Context

The brief asks for agents that negotiate "until a consensus is reached", resolved "in under 3 turns", and warns against "LLM agents talking in endless, unconstrained loops with no convergence logic / turn limits" and against "combining the 3 roles into a single prompt call". The rubric rewards LLMs for reasoning and explanation, and code for scheduling, constraints and detection.

## Decision

- The **mediator is plain code** (`mediator/core.py`). It owns turns, termination, checking, the pick rule and the fallback hand-off. It never calls an LLM.
- **Exactly three rounds:** round 1 propose (up to 10 plans per agent), round 2 score the shortlist, round 3 accept or reject the picked plan. No consensus after round 3 → the deterministic fallback decides.
- **Three separate agents, three separate calls per round,** run in parallel. Each sees only its own facts plus the other agents' stated reasons.
- **Code computes every number.** Agents choose and explain; they never compute times, fuel or costs.

## Alternatives considered

| Option | Why not |
|---|---|
| **LLM as mediator** | Termination and the pick rule would be non-deterministic and hard to audit; an LLM can be persuaded to accept. |
| **Open-ended alternating offers** until agreement | Unbounded loop, which the brief explicitly forbids. |
| **Single prompt playing all three roles** | Forbidden by the brief; also hides each domain's constraints from the others' scrutiny. |
| **Agents propose free-form plans** | Agents would invent slots or gates that don't exist; instead they pick from code-computed menus, and anything off-menu fails `C-CAP-1`. |

## Consequences

**Positive**
- Guaranteed to finish: at most 3 rounds and 9 agent calls per disruption.
- Fully reproducible in dry-run mode; every step is in the JSONL consensus log.
- An agent's malformed or refused output is retried once, then counts as a reject, so the fallback still runs.

**Negative**
- In the current build, **rounds 1–2 use each lane's code ranking even in live mode**; Claude votes only in round 3. The agents' negotiation is therefore mostly code-driven ([architecture §8](../architecture.md#8-where-the-llm-is-used-and-where-it-isnt)).
- With scripted votes, ATC's vote rule (reject anything above its own minimum delay) disagrees with the pick rule, so 10 of 32 evaluated rows end without consensus ([RESULTS.md §4](../RESULTS.md)).

## Follow-ups

- Let the Claude agents propose and score in rounds 1–2, still restricted to code-computed menus.
- Align ATC's vote tolerance with the pick rule, or pass the pick rule's reasoning to the agents in round 3.
