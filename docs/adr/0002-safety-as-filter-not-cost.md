# ADR-0002: Safety rules filter plans; they are never priced

**Status:** Accepted, with known gaps (listed below).

## Context

The brief says agents "must not accept solutions that ignore operational constraints". Both the mediator and the fallback minimise or trade off cost. Any cost-based optimiser will trade away a constraint if breaking it is priced below the saving. For safety rules that is unacceptable, and it is also not how aviation decides: safety comes from hard rules, emergency priority and the captain's authority, not from a dollar value on risk.

## Decision

Treat every safety rule as a **filter, applied before cost**:

1. Every plan from any agent or from the fallback goes through `check_plan` (`mediator/adapters.py`): capacity, wake separation (built into ATC's menu), fuel to the must-divert point, flight-crew duty, gate availability, gate-change notice, turnaround.
2. A plan that fails any hard rule is removed, with the rule ID logged. It is never priced, never shown to other agents for scoring and never returned by the fallback.
3. The picked plan is checked again after the vote, before it leaves the mediator.
4. If no plan passes, the system recommends cancellation to the duty manager and applies nothing.
5. The duty manager approves or rejects every outcome.

Fuel is measured to the point where the aircraft must leave for its alternate; the 30-minute final reserve is never touched. Ground-crew overtime is the only constraint priced as a soft cost, because it's a labour cost rather than a safety limit.

## Alternatives considered

| Option | Why not |
|---|---|
| **Large penalty cost per violation** | Any finite penalty can be outweighed by a large enough saving, and the penalty value becomes an arbitrary safety-for-money exchange rate. |
| **Let the LLM agents judge safety** | The brief and rubric reject LLM-only legality checks; models can be talked into unsafe agreements (sycophancy). |
| **Value of a statistical life in the objective** | Regulators use it for rule-making, not live operational decisions. Inappropriate here. |

## Consequences

**Positive**
- No amount of saving can buy a rule violation.
- 0 hard-rule violations reached the duty manager in 32 evaluated rows; the checker removed 139 of 604 proposed plans ([RESULTS.md](../RESULTS.md)).
- Every rejection carries a rule ID, so the duty manager can see why a plan was dropped.

**Known gaps**
- **The fallback ignores why an agent rejected a plan.** In 7 of 10 no-consensus rows it returned the plan an agent had just rejected. Those rejections were about delay, not safety, but a Pilot safety concern that the checker doesn't model would be overridden the same way.
- **Fuel flags don't reach the mediator.** The ATC lane implements FAA meanings (`MINIMUM_FUEL`: no added holding; `EMERGENCY_FUEL`: earliest slot), but a `Vote` carries only accept/reject and a reason.
- **Cost minimisation pushes plans toward the edge of the rules.** A plan with 0.1 min of fuel margin passes the same as one with 18 min. In the evaluation every chosen plan had 17–21 min of margin, but because holding plans were unavailable (a separate bug, [RESULTS.md §5](../RESULTS.md)), not by design.
- **The mediator's fallback never considers diversion.** Safe for a flight still on the ground; not for one already airborne.

## Follow-ups

Make the fallback rank in strict priority order, with cost last:

1. Hard rules filter (as now).
2. `EMERGENCY_FUEL` → earliest valid slot, regardless of cost.
3. `MINIMUM_FUEL` → no added holding, no later slot.
4. Prefer plans with a fuel margin ≥ 10 min.
5. Exclude any plan the Pilot rejected on safety grounds.
6. Then cheapest.
7. Escalate to the duty manager when the best plan has a thin margin or the only options are divert or cancel.

This needs flags added to `Vote` and about 30 lines in `fallback/scenario.py` and `mediator/core.py`.
