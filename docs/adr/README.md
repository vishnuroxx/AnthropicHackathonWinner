# Architecture decision records

Each record captures one design choice: the context, what we decided, the alternatives we weighed and what it costs us. Format: [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-nash-product-pick.md) | The mediator picks the plan with the highest Nash product of agent scores and a cost score | Accepted |
| [0002](0002-safety-as-filter-not-cost.md) | Safety rules filter plans out before any cost is computed; they are never priced | Accepted, with known gaps |
| [0003](0003-code-mediator-fixed-three-rounds.md) | A pure-code mediator runs exactly three rounds; the LLM never decides termination | Accepted |

Records 0001–0003 were written after the hackathon (1 Nov 2026) from the code, commit history and team design docs. Where the reasoning wasn't written down at the time, the record says so.
