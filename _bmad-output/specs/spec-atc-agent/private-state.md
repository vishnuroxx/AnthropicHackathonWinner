# ATC Private State

Facts only the ATC agent receives (computed by code, per `CLAUDE.md` §6–7).

| Fact | Source | Provenance | Used for |
|---|---|---|---|
| Event type + magnitude | `WEATHER_DELAY` / `LATE_AIRCRAFT_DELAY` | real | Shared with all agents |
| Focal flight (id, airline, tail, origin→dest, scheduled dep/arr, scheduled time, distance) | DOT row | real | Shared with all agents |
| Arrival slot grid (e.g. 5-min slots) | Rule | synthetic | Which slots exist and which are free |
| Capacity window (reduced capacity during weather) | Rule | synthetic | How many slots are usable when |
| Background arrivals (slots occupied) | Other DOT rows, same dest + date + hour | real schedule | Knock-on delay; re-sequencing |
| Weight class per arrival | Airline rule: MQ / EV / OO = regional, others = mainline | synthetic rule | Spacing |
| `MINIMUM_FUEL` flag | Pilot message (via log) | from agent | Priority (CAP-8) |

## Responsibilities and interests

- **Owns:** the arrival-time decision. Options: a new slot via ground delay (delay take-off) or airborne holding. The Pilot accepts or counters.
- **Objectives:** throughput; separation; minimise total system delay (focal + knock-on).
- **Speaks for:** background flights, which don't negotiate.
- **Can offer:** re-sequencing; a different slot.
- **Must:** prioritise a flight flagged `MINIMUM_FUEL`.
- **Checker check it relates to:** slot — slot free, within reduced capacity, spacing by weight class.
- **Cost context:** airborne holding costs more per minute than ground delay (no fuel burn on the ground); knock-on delay to background flights is costed at the same per-minute rates.
