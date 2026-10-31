# ADR-0001: Pick the plan with the highest Nash product

**Status:** Accepted. Rationale written after the fact (1 Nov 2026); the switch from the framing doc's rule wasn't recorded at the time.

## Context

After round 2, the mediator holds a shortlist of safe plans, each scored 0–1 by ATC, Pilot and Ground. It needs a deterministic rule to pick one for the final vote. The agents' objectives are in different units: ATC minimises system delay in minutes, the Pilot protects fuel margin and connections, and Ground minimises gate and crew cost in dollars. The airline also cares about total cost.

The design doc ([challenge-2-framing.md §3](../challenge-2-framing.md), rule 5) specified "maximise the minimum agent utility". The implementation (`nash_pick` in `mediator/core.py`) uses the Nash product instead.

## Decision

Pick the plan with the highest **ATC score × Pilot score × Ground score × cost score**, where cost score = cheapest shortlisted cost ÷ this plan's cost. Scores are floored at 0.05 so a single 0 can't act as a veto; vetoes belong to the safety checker ([ADR-0002](0002-safety-as-filter-not-cost.md)). Ties go to the lower cost, then the lower plan ID.

## Alternatives considered

| Rule | Why not |
|---|---|
| **Least cost only** | That is the fallback solver. It ignores what the agents said, so there would be nothing to negotiate. |
| **Sum of scores** (utilitarian) | Needs an exchange rate between minutes, fuel and dollars. Lets two agents outvote the third into its worst plan. |
| **Maximise the minimum score** (egalitarian; the original design) | Protects the worst-off agent but ignores gains to everyone else. With rank-based scores, ties are frequent. |
| **Kalai–Smorodinsky** | Needs each agent's ideal point; more machinery for a 3-to-9-plan shortlist. |
| **Voting** (Borda, majority) | Three voters can cycle; ties are common; it can't express how much an agent cares. |

## Consequences

**Positive**
- Never picks a plan that another shortlisted plan beats for every agent (Pareto efficiency).
- Doesn't need the agents' units converted into one currency.
- Favours balanced compromises: one unhappy agent pulls the product down. It sits between "sum" and "maximise the minimum".
- Cost is a fourth factor, so a balanced plan can't be wildly expensive.

**Negative / deviations from the textbook Nash bargaining solution**
- **Gains are measured from 0, not from the disagreement point.** The real outcome of no deal is the fallback plan, so an agent can be handed a plan worse for it than no deal at all.
- **Scores are ranks, not utilities.** Each lane scores by position among the shortlisted plans (best 1.0, worst 0.0). Adding or removing one plan changes every other plan's score, so scale invariance holds only partly.
- **The floor of 0.05 weakens protection** for an agent that ranks a plan last.

## Evidence

- Unit tests: `test_nash_balanced_plan_beats_lopsided_one`, `test_nash_cost_factor_and_floor` in `mediator/test_core.py`.
- Demo row (DFW, MQ3086, 24 Apr 2015): the Nash pick costs $1,110 more than the least-cost plan on the shipped cost model, but $18,090 less once missed connections are priced ([RESULTS.md §3](../RESULTS.md)).
- Over 31 evaluated rows, the negotiated plan equals the least-cost solver's in 29 ([RESULTS.md §4](../RESULTS.md)): balance rarely costs money.

## Follow-ups

- Score agents by real utility (minutes, fuel margin, dollars) normalised to each agent's range, and measure gains from the fallback plan.
