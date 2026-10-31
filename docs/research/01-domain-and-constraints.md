# Research: ATM domain facts and constraint values (Challenge #2)

Research-agent report, 31 Oct 2026. faa.gov returned 403, so FAA wake tables are from secondary sources only. **Encode ICAO values (via SKYbrary/Wikipedia citing ICAO Doc 4444) and cite ICAO.**

## Amendments: what changed and why
The provided data did not change any constraint values. These amendments reconcile this report with the others and with the hackathon constraints.

| # | Previously stated | Amended to | Why |
|---|---|---|---|
| D1 | The data report's separation matrix used "else 3 NM" as the minimum when no wake pair applies; this report says the ICAO default is 5 NM, with 3 NM common in terminal areas | The checker uses **3 NM as a stated assumption** (rule C-SEP-1), with 5 NM as the ICAO reference | The two reports conflicted. 3 NM is typical of terminal operations, but we couldn't verify it from a primary source (FAA site blocked), so it must be presented as an assumption, not a fact |
| D2 | Holding burn: this report gives 25 kg/min (Airbus, primary); the data report gives 2,300 kg/h (~38 kg/min) | **25 kg/min is the default**; ~38 kg/min is the sensitivity upper bound | Prefer the primary manufacturer source; keep the other as a range, so the fuel numbers are honest about their uncertainty |
| D3 | The constraint table mixes ICAO and FAA values | **Encode ICAO values on US (DOT) data**, and say so on the slide | The data is US, but FAA primary sources were unreachable (403). The heavy-aircraft wake pairs agree between ICAO and FAA, so the mismatch is small and disclosed |
| D4 | Cancellation or diversion could be part of a recovery | **Excluded from the option set** | The provided dataset has 0 cancelled and 0 diverted flights (see `04-data-and-evaluation.md` A7), so we can't ground or evaluate those actions |

## 1. Named user and status quo
**Named user:** airline Operations Control Centre (OCC) duty manager / flight dispatcher at a US hub, coordinating with the FAA traffic management coordinator (TMC) and the ramp / ground-handling supervisor.

Today:
- When weather or a runway closure cuts capacity, FAA lowers the Airport Arrival Rate (AAR) and issues a Ground Stop or Ground Delay Program (GDP) with a program rate and an EDCT per flight. https://www.fly.faa.gov/ois/help/index.html · https://en.wikipedia.org/wiki/Ground_delay_program
- Local ground stop ≤ 15 min without ATCSCC, ≤ 30 min total, then usually a GDP. https://nbaa.org/aircraft-operations/airspace/tfm/tools-used-for-traffic-flow-management/ground-stop-gs/
- Coordination by planning telcons (e.g. ORD event planning telcon on runway configs before setting a GDP rate). https://www.fly.faa.gov/Information/west/zau/ord/ord_tm.htm
- Airlines see demand in Flight Schedule Monitor / TFMS; dispatchers swap EDCT slots among own flights (slot substitution). https://nextor.umd.edu/files/2019/02/2003_JPO_UMD_Benefits-CDM-in-ATM-16h9lc9.pdf · ICAO APAC ATFMSG-14 WP06
- Europe (A-CDM): handler enters TOBT → sequencer issues TSAT → TTOT = TSAT + variable taxi; take-off within TTOT ±5 min. https://www.dublinairport.com/docs/default-source/default-document-library/a-ground-handlers-guide-to-a-cdm_eidw.pdf · https://www.icao.int/MID/Documents/2023/ACDM/PPT_5%20-%20ACDM%20Milestones%20approach.pdf
- **Gap we target (inference, not measured in sources):** the gate/stand, crew and connection side of the trade-off is still phone and radio between OCC, ramp and tower.

## 2. Cost numbers
- **US block-time cost:** $98.41/min in 2025 (crew $37.01, fuel $29.34, maintenance $18.35); 2024 $100.76; passenger time $47/h. https://airlines.org/dataset/u-s-passenger-carrier-delay-costs/
- **Eurocontrol tactical delay cost incl. knock-on (2022 prices):** at gate €166/min (all) / €45 (<30 min); taxi €182 / €62; **airborne holding €206 / €84**. A320 15-min delay: €594 at gate vs €1,187 airborne → absorb delay on the ground. Network ATFM average €100/min. https://standard-inputs.netlify.app/chapters/cost_of_delay.html
- **Europe 2024:** 29.6M ATFM delay minutes ≈ €3.9B. https://www.eurocontrol.int/publication/high-level-summary-report-preliminary-ace-2024-data
- **Reactionary delay:** 46% of European delay minutes in 2024 (8.0 of 17.5 min/flight). https://www.eurocontrol.int/publication/all-causes-delays-air-transport-europe-annual-2024
- **US causes (BTS, Aug 2026, % of flights):** late aircraft 10.16% (largest), NAS 7.45%, carrier 7.29%, extreme weather 1.06%; weather that slows ops is coded NAS (45.8% of NAS delay in 2020). https://www.transtats.bts.gov/OT_Delay/OT_DelayCause1.asp · https://www.bts.gov/topics/airlines-and-airports/understanding-reporting-causes-flight-delays-and-cancellations
- **Holding fuel:** Airbus — A320 family ~100 kg per 4-min standard hold ≈ **25 kg/min**. https://www.airbus.com/sites/g/files/jlcbta136/files/2021-11/Backgrounder-EN-Most-Efficient-Flight.pdf (rules of thumb 25–45 kg/min, unofficial; no primary B737 figure).

## 3. Constraint table for the checker
| Constraint | Value | Source |
|---|---|---|
| Wake separation on approach (ICAO, radar) | H→H 4 NM; H→M 5; H→L 6; M→L 5; Super(J)→H 5; J→M 7; J→L 8 | ICAO Doc 4444 §8.7.3 via https://en.wikipedia.org/wiki/Wake_turbulence_category · https://skybrary.aero/articles/mitigation-wake-turbulence-hazard |
| Minimum radar separation, no wake pair | 5 NM ICAO default; 3 NM common in terminal areas (3 NM unverified) | Doc 4444 via SKYbrary |
| Reduced separation on final | 2.5 NM within 10 NM of threshold if avg runway occupancy ≤ 50 s | https://www.faa.gov/documentLibrary/media/Notice/N7210.765.pdf · https://trid.trb.org/View/143987 |
| FAA legacy wake | H→H 4; H→Large 5; H→Small 6 (secondary). Super/B757 values from memory, unverified | JO 7110.65 ¶5-5-4 (403) |
| Fuel reserve, US Part 121 domestic | Destination + most distant alternate + 45 min normal cruise | 14 CFR 121.639 https://www.law.cornell.edu/cfr/text/14/121.639 |
| Fuel reserve, Part 91 IFR | Destination + alternate + 45 min | 14 CFR 91.167 https://www.law.cornell.edu/cfr/text/14/91.167 |
| Final reserve, ICAO/EASA | 30 min holding at 1,500 ft above alternate/destination, ISA | https://www.skybrary.aero/articles/fuel-flight-planning-definitions |
| Contingency fuel, ICAO | Greater of 5% trip fuel or 5 min holding at 1,500 ft (check Annex 6 wording) | SKYbrary; ICAO ESAF FAA presentation |
| Narrow-body turnaround (Europe) | Scheduled median 45 min (P10–P90 25–80); actual median 52 (31–93) | https://standard-inputs.netlify.app/chapters/turnaround_time.html |
| Minimum connection time | Domestic ~30–60 min by airport; intl→dom 90–120 | https://www.oag.com/minimum-connection-time (secondary) |
| A-CDM departure tolerance | Take-off within TTOT ±5 min | Dublin A-CDM guide |

## 4. Existing tools (positioning)
- AMAN/DMAN: SESAR DMAN validation — taxi time −9%, slot adherence 76% → 81%. https://www.sesarju.eu/node/627 · CP1 AMAN/DMAN integration still in progress (CDG, Nice) in 2025. https://www.eurocontrol.int/sites/default/files/2026-09/eurocontrol-implementation-plan-report-2025.pdf
- A-CDM: fewer wasted slots, protects capacity in disruption. https://trimis.ec.europa.eu/project/airport-collaborative-decision-making
- FAA: TFMS, Flight Schedule Monitor, ATCSCC. ICAO APAC ATM SG/11 IP06.
- Airbus: Skywise lists disruption management; Navblue merged into Skywise Apr 2026. https://aviationweek.com/aerospace/emerging-technologies/airbus-launches-new-open-aviation-data-platform-support-digital · https://www.aircraft.airbus.com/en/services/operate
- **Positioning (inference):** each tool optimises one stakeholder; none negotiates ATC + pilot + ground trade-offs jointly with a full audit log.

## 5. Label as simplified / synthetic
- Fuel on board (not in DOT data): "reserve + X min"; burn 25–45 kg/min is an assumption.
- Wake category: inferred from aircraft type (tail → registry) or synthetic.
- Simplified model: ICAO wake values, single runway, optional 2.5 NM/50 s rule; no time-based departure separation, no RECAT/CWT.
- Gates, crew shifts, connections: synthetic. **No authoritative ground-crew overtime norm found** → state the shift limit (e.g. 8 h + cap) as an assumption.
- Part 117 pilot duty: not researched; leave out.
- Don't add USD (A4A) and EUR (Eurocontrol) figures together.

## Could not verify
JO 7110.65 ¶5-5-4 tables; exact Annex 6 clause/contingency wording; primary B737 holding burn; Airbus turnaround figure; ground-crew overtime norms; IATA MCT database values.
