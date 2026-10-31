# ATC Research

ATC-relevant facts only; for builders, not loaded by the agent. ✅ primary, 🟡 secondary, ❌ unverified. Agreed scope: `CLAUDE.md`. A1–A3 are references for the spacing values (open question); A6 is out of MVP scope (no taxiway events).

| # | Fact | Status | Source |
|---|---|---|---|
| A1 | Wake separation on approach (ICAO radar): H→H 4 NM, H→M 5, H→L 6, M→L 5; J→H 5, J→M 7, J→L 8 | 🟡 | ICAO Doc 4444 §8.7.3 via [SKYbrary](https://skybrary.aero/articles/mitigation-wake-turbulence-hazard) |
| A2 | Minimum separation with no wake pair: ICAO default 5 NM; 3 NM in terminal areas is a team assumption (C-SEP-1) | ❌ | SKYbrary |
| A3 | Reduced separation on final: 2.5 NM within 10 NM of threshold if average runway occupancy ≤ 50 s | 🟡 | [FAA N7210.765](https://www.faa.gov/documentLibrary/media/Notice/N7210.765.pdf) |
| A4 | When capacity drops, the FAA lowers the airport arrival rate and issues a ground stop or Ground Delay Program with an EDCT per flight; departure within EDCT ±5 min | 🟡 | [FAA OIS](https://www.fly.faa.gov/ois/help/index.html), [Wikipedia: GDP](https://en.wikipedia.org/wiki/Ground_delay_program) |
| A5 | ATL ~250 total ops/h (FAA capacity profile 2018); ~132 arrivals/h optimal (analyst); poor ceiling/visibility can cut arrivals ~30% | 🟡 | [FAA ATL profile](https://www.faa.gov/sites/faa.gov/files/airports/planning_capacity/profiles/ATL-Airport-Capacity-Profile-2018.pdf), [Aerology](https://aerology.substack.com/p/some-predictions-and-prescriptions), [AMS](https://ams.confex.com/ams/pdfpapers/101444.pdf) |
| A6 | Planned taxiway closures are published in public NOTAMs | 🟡 | [FAA NOTAM examples](https://www.faa.gov/air_traffic/publications/atpubs/notam_html/appendix_a.html) |
| A7 | Airlines see arrival demand in Flight Schedule Monitor / TFMS and swap EDCT slots among their own flights | 🟡 | [NEXTOR CDM benefits](https://nextor.umd.edu/files/2019/02/2003_JPO_UMD_Benefits-CDM-in-ATM-16h9lc9.pdf) |
| A8 | Airborne holding costs about twice gate delay (A320, 15 min: €1,187 vs €594); holding burns ~25 kg/min (A320) | ✅ | [Eurocontrol standard inputs](https://standard-inputs.netlify.app/chapters/cost_of_delay.html), [Airbus](https://www.airbus.com/sites/g/files/jlcbta136/files/2021-11/Backgrounder-EN-Most-Efficient-Flight.pdf) |
| A9 | FAA JO 7110.65 ¶5-5-4 wake tables could not be fetched (403) | ❌ | — |
