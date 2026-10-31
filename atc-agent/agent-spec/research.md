# ATC Research

ATC-relevant facts only; for builders, not loaded by the agent. ✅ primary, 🟡 secondary, ❌ unverified. Agreed scope: `CLAUDE.md`. **A1–A3, A5 and A9 are superseded** by the organiser workbook `data/raw/challenge2/challenge-2-operational-constraints.xlsx` (sheets `wake_separation`, `airport_capacity`); kept as background only. A5's ~30% weather cut is still the reference for the weather reduction factor. A6 is out of MVP scope (no taxiway events).

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
| A10 | FAA wake weight classes by max take-off weight: Small ≤ 41,000 lb; Large 41,000–300,000 lb; Heavy ≥ 300,000 lb; Super = A380; B757 Large but Heavy-like when leading. CRJ/ERJ/737/A320 are Large | 🟡 | [Wikipedia: Wake turbulence category](https://en.wikipedia.org/wiki/Wake_turbulence_category) |
| A11 | Approach speeds: 737-700 130 kt, 737-800 142 kt (FAA AC 150/5300-13); ICAO approach category C 121–140 kt, D 141–165 kt | 🟡 | [Wikipedia: Aircraft approach category](https://en.wikipedia.org/wiki/Aircraft_approach_category) |
| A12 | DFW total ops/h (FAA capacity profile 2018): VMC south ~199–204, marginal 187–192, IMC 168–170 → IMC cut ≈ 17% | 🟡 | [FAA DFW profile 2018](https://www.faa.gov/sites/faa.gov/files/airports/planning_capacity/profiles/DFW-Airport-Capacity-Profile-2018.pdf) (via search excerpt; PDF returned 403) |
| A13 | DFW 2015: 681,261 aircraft movements (~933 arrivals/day); flights.csv has 203 DFW arrivals on 24 Apr 2015 (≈ 22%) | 🟡 | [2015 airport rankings](https://www.miami-airport.com/library/pdfdoc/Cargo%20Documents/2015_Rankings-US_and_Worldwide_(Final).pdf) |
| A14 | SFO lands up to 54/h in visual, at best 36/h in instrument conditions (33% cut) | 🟡 | [AMS 2008 paper](https://ams.confex.com/ams/pdfpapers/134479.pdf) |
| A15 | A minimum-fuel advisory is not an emergency; it signals no undue delay can be accepted | 🟡 | [FAA JO 7110.65 ch. 2 §1](https://www.faa.gov/air_traffic/publications/atpubs/atc_html/chap2_section_1.html) (via ICAP S5) |
