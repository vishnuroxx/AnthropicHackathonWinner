# ATC Private State

Facts only the ATC agent receives (computed by code). Limits come from the organiser workbook `data/raw/challenge2/challenge-2-operational-constraints.xlsx`.

| Fact | Source | Provenance | Used for |
|---|---|---|---|
| Event type + magnitude | `WEATHER_DELAY` / `LATE_AIRCRAFT_DELAY` | real | Shared with all agents |
| Focal flight (id, airline, tail, origin→dest, scheduled dep/arr, scheduled time, distance) | DOT row | real | Shared with all agents |
| Runway capacity (`active_runways`, `max_runway_ops_per_hour`) | Workbook `airport_capacity` | organiser (synthetic) | Arrival cap |
| Arrival cap per hour | 50% of runway ops/h (45 at DFW) | derived | Slot grid |
| Weather window + cut | Hours with clustered weather-delayed arrivals in flights.csv; 30% cut (31/h at DFW); sensitivity run 17% (37/h) | real window, synthetic cut | Reduced capacity |
| Background arrivals | Other DOT rows, same dest + date, focal hour ± 1 h | real schedule | Knock-on delay |
| Filler arrivals | Added so demand/h ≈ 2.06 × file arrivals/h (scaled like capacity); airline `SYN`, seeded times | synthetic | Realistic congestion (flights.csv holds delayed flights only) |
| Wake class per arrival | Default `Large`; override table by tail or airline | synthetic, adjustable | Spacing |
| Minimum gap per leader → follower pair | Workbook `wake_separation` (NM) at 140 kt approach speed | organiser + derived | Spacing |
| Option menu (id, slot, ground delay, holding, knock-on, total system delay, cost, spare slots in hour, valid) | Code (checker + cost) | derived | What ATC may propose or accept |
| Fuel flags (`MINIMUM_FUEL`, `EMERGENCY_FUEL`) | Pilot message (via log) | from agent | CAP-8 |

## Responsibilities and interests (see `icap.md`)

- **Owns:** the arrival-time decision: a new slot via ground delay (delayed take-off) or airborne holding. The Pilot accepts or counters.
- **Objectives:** safety first (hard); then lowest total system delay (focal + knock-on). Prefers stable plans (CAP-10) and flags thin margins (CAP-11).
- **Speaks for:** background flights, which don't negotiate.
- **Can offer:** a different menu option.
- **Fuel:** `MINIMUM_FUEL` → no added holding, no later slot. `EMERGENCY_FUEL` → earliest valid option.
- **Checker check it relates to:** slot — within the hourly arrival cap, spacing by wake pair.
- **Cost context:** airborne holding costs more per minute than ground delay. Knock-on delay to background flights is costed at the same per-minute rates.
