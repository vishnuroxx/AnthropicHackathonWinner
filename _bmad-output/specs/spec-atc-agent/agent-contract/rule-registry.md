> Copied from ../../spec-agent-contract/ on 2026-10-31; source of truth is there.

# Rule registry — contract v0.2 hybrid

Companion to `SPEC.md`. Every `rule_id` in a check comes from this table. Workbook values (`data/raw/challenge2/challenge-2-operational-constraints.xlsx`) override `CLAUDE.md` and the framing doc (`docs/challenge-2-framing.md` lines 103–111). Ruleset id: `challenge2-workbook-2026-10-31`.

Owner: checker code (team B) evaluates every rule. "Agent that cares" is the agent whose interests the rule protects; it argues from the check result and never decides validity.

| rule_id | limit | hard / soft | source | agent that cares |
|---|---|---|---|---|
| `C-WAKE-1` | leader→follower spacing by wake class (table below) | hard | workbook `wake_separation` | ATC |
| `C-SEP-1` | any other known pair: 3 NM = 77 s | hard | workbook `wake_separation` (framing doc called it an assumption) | ATC |
| `C-CAP-1` (new) | arrivals per hour ≤ 45 normal (50% of the workbook's 90 ops/h); ≤ 31 in the weather window (30% cut); ≤ 37 sensitivity run (17% cut) | hard | workbook `airport_capacity` + research | ATC |
| `C-RWY-1` | closed runway forbidden | hard | out of MVP scope; checker does not implement | ATC |
| `C-FUEL-1` | `holding_min` ≤ 45 + `extra_fuel_min`; the 30-min final reserve is never used | hard | workbook `fuel_and_crew` | Pilot |
| `C-FUEL-2` | replaced by the flag semantics (`SPEC.md` CAP-6): `MINIMUM_FUEL`, `EMERGENCY_FUEL` | hard | FAA | Pilot |
| `C-GATE-1` | no gate double-booking; DFW 150 gates, 3 spare | hard | workbook `airport_capacity` | Ground |
| `C-GATE-2` (new) | a gate change needs ≥ 20 min notice | hard | workbook `fuel_and_crew` | Ground |
| `C-TURN-1` | turnaround ≥ 45 min (overrides the framing doc's 25) | hard | workbook `airport_capacity` | Ground |
| `C-CREW-1` | ground crew 8 h, then overtime at 1.5× | soft (cost) | workbook `fuel_and_crew` | Ground |
| `C-CREW-2` (new) | flight crew duty ≤ 13 h | hard | workbook `fuel_and_crew` | Pilot |
| `C-MCT-1` | domestic connection 30–60 min, per airport; unchanged | hard | framing doc | Ground |

## C-WAKE-1 spacing

Converted from NM to time at a fixed 140 kt approach speed (wind ignored; synthetic, stated in the demo).

| leader → follower | NM | seconds at 140 kt |
|---|---|---|
| Super → Heavy | 6 | 154 |
| Super → Large | 7 | 180 |
| Super → Small | 8 | 206 |
| Heavy → Heavy | 4 | 103 |
| Heavy → Large | 5 | 129 |
| Heavy → Small | 6 | 154 |
| Large → Small | 4 | 103 |
| any other known pair (`C-SEP-1`) | 3 | 77 |

## Notes

- **Wake class:** DOT rows carry no aircraft type, so every flight defaults to Large (regional jets are Large, not Small), adjustable by an override table. With the default every pair is Large→Large and `C-SEP-1` governs.
- **Weather window:** hours with clustered `WEATHER_DELAY > 15` arrivals at the destination in `flights.csv` (real). DFW 24 Apr 2015: 11–13 h, 17 h, 19–20 h.
- **Arrival count:** `C-CAP-1` counts real `flights.csv` arrivals plus labelled synthetic filler, scaled by the same 0.45 as capacity (world builder, team B).
- **New ids:** `C-CAP-1`, `C-GATE-2`, `C-CREW-2` carry workbook values that had no id in the framing doc.
- **Fuel:** the 45-min spare is on top of the 30-min final reserve. `C-FUEL-1` limits holding, never the reserve.
- **Units:** separation rules report seconds in a check (`unit: "s"`); all other times are minutes.
