# Agent agreement: ATC · Pilot · Ground (PROPOSED)

Three independent agents. They share one thing: the message they send to the middleman.
Everything else is private to each agent. Lane owners: object by 15:00 or it stands.

## Shared: the message (so the middleman, which is code, can read it)
| Field | Meaning |
|---|---|
| `action` | `propose` · `accept` · `counter` · `reject` |
| `plan_id` | the table plan you accept (e.g. `P2`) |
| `plan` | slot, ground delay, holding, extra fuel, gate, divert (leave a field `null` if it's not yours) |
| `reason` | one line: why |

## Private: everything else (each agent decides its own)
| | Decides | Protects | Own constraints, ranking, fallback |
|---|---|---|---|
| ATC | arrival slot | throughput, background flights | its own |
| Pilot | divert, extra fuel | fuel, crew duty, connections | its own |
| Ground | gate | gates, ground crew, next departure | its own |

Common ground: safety first, and keep the operation moving. Each agent enforces its own hard limits
in code and never accepts a plan that breaks them; it rejects and gives the reason.

## Fix so they can read each other
- `plan.gate` must accept `null` (ATC sends `null` today and fails the shared schema).
