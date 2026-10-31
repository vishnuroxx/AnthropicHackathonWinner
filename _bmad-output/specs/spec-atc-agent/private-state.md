# ATC Private State

Loaded only by the ATC agent (and code that checks ATC rules). Provenance per `docs/challenge-2-framing.md` §6.

| Item | Provenance | Detail | Used for |
|---|---|---|---|
| Landing queue | real | Other delayed arrivals at the destination airport in the scenario hour ±1–2 h. On-time background traffic, if used, is synthetic. | Ripple effects; leader/follower pairs for wake checks |
| Wake category per arrival | enriched / synthetic | FAA registry (tail → type → category); synthetic mix if the match rate is low | C-WAKE-1 |
| Arrival capacity per hour | synthetic | METAR → capacity rule (e.g. 60 → 40/h in weather). Scale reference: ATL ~132/h optimal, up to ~30% lower in poor weather | Throughput; how many arrivals fit per slot |
| Runway configuration | enriched | Runways from OurAirports (current, not 2015) | C-RWY-1; sequencing |
| Sudden taxiway/runway blockages | synthetic | Unplanned blockages and until when. Planned closures are scenario NOTAMs (shared) | C-RWY-1 |
| Utility weights | code | Fixed weights for ATC goals; never in the LLM | Ranking (CAP-2) |
| Preference bounds | code | Bounds ATC may relax when conceding (values open) | Concession (CAP-5) |

## Responsibilities and interests

- **Responsibilities (brief):** runway wake separation; taxiway blockage; maximise sector throughput.
- **Rules ATC argues from:** C-WAKE-1, C-SEP-1, C-RWY-1. C-FUEL-2 (low-fuel flights can't be resequenced later) constrains ATC sequencing but belongs to the Pilot side.
- **Interests:** keep arrivals within capacity; minimise airborne holding (it costs about twice gate delay); minimise ripple on other arrivals; reduce AIR_SYSTEM and WEATHER delay minutes (open question).
- **May reveal:** capacity and until when; how many arrivals a slot pushes back; blocked runway/taxiway.
