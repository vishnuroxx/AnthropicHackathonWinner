# Research: dataset, digital twin and evaluation (Challenge #2)

Research-agent report, 31 Oct 2026, **amended the same day after the organisers' data arrived**. Original items marked [UNVERIFIED] were from memory. Items marked **[VERIFIED ON DATA]** were checked against the provided files.

## Amendments: what changed and why

The original report was written before we had the organisers' files. It assumed we would get the **full Kaggle "2015 Flight Delays and Cancellations" dataset** (5.8M rows, every scheduled flight). The organisers instead provided a **pre-filtered subset**, which matches the brief's instruction ("pick any row with WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20"). Profiling `data/raw/dot2015/flights.csv` showed:

| # | Previously assumed | What the provided data shows | Why the assumption fails | Change made |
|---|---|---|---|---|
| A1 | `flights.csv` is the full 5,819,079-row, ~565–590 MB file | **358,774 rows, 38.6 MB.** Every row meets the brief's filter (42,012 weather > 15; 326,249 late aircraft > 20) | The organisers pre-filtered the data to the challenge condition | §1 rewritten with real counts |
| A2 | We can rebuild the **full demand bank** (all arrivals and departures at airport X in hour h) | **No on-time flights** (0 rows with `ARRIVAL_DELAY < 15`) | On-time traffic was filtered out, so real runway and gate occupancy is unknown | §2: the bank is now **the delayed arrivals at X in hour h** (real). On-time background traffic, if needed, is **seeded synthetic and labelled** (§4) |
| A3 | Full **tail rotations** give each aircraft's next leg and the real downstream delay | Only *delayed* legs exist: 89,853 of 206,533 tail-days have ≥ 2 delayed legs, giving 144,746 linked leg pairs (destination = next origin) | A tail's on-time legs are missing, so chains have gaps | §2: rotations are **partial**. Use linked pairs where they exist; otherwise synthesise the next leg. B0 "do-nothing cascade" and the "real downstream delay" context are only computable on linked pairs |
| A4 | October uses numeric BTS airport IDs, so October must be excluded or remapped | **No October rows at all**; all codes are IATA | Not in the subset | Quirk removed; no remapping needed |
| A5 | Delay-cause columns are NaN unless `ARRIVAL_DELAY ≥ 15` | **All cause columns are filled** on every row | Every row is already delayed ≥ 15 min | Null handling for cause columns dropped |
| A6 | Times are hhmm **integers** (e.g. `5` = 00:05) | Times are **zero-padded strings** (`"0648"`); `2400` appears in 425 rows | Different export from the Kaggle version | Read time columns as strings; map `2400` to 00:00 the next day |
| A7 | `TAIL_NUMBER` may be null on cancelled flights; cancellations and diversions present | **0 cancelled, 0 diverted, 0 null tails** | Filtered out | Cancellation/diversion handling not needed. **Cancelling or diverting a flight must not be a recovery option**, because we have no real cancelled/diverted cases to compare against |
| A8 | Evaluation baselines can be compared with the *full* real outcome of the day | Only the delayed subset is known | The real counterfactual is unobservable either way, and now partial too | "Real downstream delay" remains **context only**, restricted to linked pairs |

**Unchanged:** enrichment sources (§3), the evaluation design (§5) and the optimisers (§6) still apply. Sampling by airport tier × cause is still feasible, because both causes are present at many airports.

## 1. Dataset (provided subset) [VERIFIED ON DATA]
Derived from BTS On-Time Performance 2015 (the same source as Kaggle usdot/flight-delays), **pre-filtered by the organisers**.
- `flights.csv`: **358,774 rows, 31 columns, 38.6 MB.** All rows have `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`. 11 months (no October), 334 distinct days. 14 carriers (WN 94,962 rows, most).
- `airports.csv`: 322 rows (IATA_CODE, AIRPORT, CITY, STATE, COUNTRY, LATITUDE, LONGITUDE).
- `airlines.csv`: 14 carriers.
- Top destinations by delayed arrivals: ORD 21,584 · ATL 18,504 · DFW 17,310 · DEN 14,316 · LAX 13,863.
- Densest disrupted arrival hours: ATL 30 Dec 15:00 (58 delayed arrivals, mean 101 min, mostly late aircraft) · ATL 18 Jun 21:00 (49) · DFW 13 Apr 17:00 (43, more weather/carrier mix).

| Column(s) | Meaning / units |
|---|---|
| YEAR, MONTH, DAY, DAY_OF_WEEK | Date (DOW 1=Mon..7=Sun) |
| AIRLINE, FLIGHT_NUMBER, TAIL_NUMBER | IATA carrier, flight number, N-number (never null here) |
| ORIGIN_AIRPORT, DESTINATION_AIRPORT | IATA codes (no numeric IDs in this subset) |
| SCHEDULED_DEPARTURE, DEPARTURE_TIME | Local time, **zero-padded string hhmm**; `2400` can appear |
| DEPARTURE_DELAY | Minutes (negative = early) |
| TAXI_OUT, WHEELS_OFF | Minutes; hhmm local |
| SCHEDULED_TIME, ELAPSED_TIME, AIR_TIME | Minutes |
| DISTANCE | Statute miles |
| WHEELS_ON, TAXI_IN | hhmm local; minutes |
| SCHEDULED_ARRIVAL, ARRIVAL_TIME | Destination-local hhmm string; no arrival date (overnight wraps) |
| ARRIVAL_DELAY | Minutes (always ≥ 15 here) |
| DIVERTED, CANCELLED | Always 0 here |
| CANCELLATION_REASON | Empty here |
| AIR_SYSTEM_DELAY, SECURITY_DELAY, AIRLINE_DELAY, LATE_AIRCRAFT_DELAY, WEATHER_DELAY | Minutes; **always filled**; sum to ARRIVAL_DELAY |

Quirks
- Delay causes are arrival-side, so the disruption is an **arrival bank at DESTINATION_AIRPORT**.
- Times are local to each airport with no time-zone column. Same-airport arithmetic is safe; cross-airport needs a time zone (e.g. `timezonefinder` on lat/lon).
- Read times as strings. Small enough to load whole, but cache one airport-day to parquet for speed.

## 2. Rebuildable from real data (amended)
- **Disrupted arrival bank (real):** delayed arrivals with DEST = X in hour h (±1–2 h). This is a *subset* of real traffic (A2).
- **On-time background traffic (synthetic, optional):** if runway or gate load must look realistic, add seeded on-time arrivals at a stated rate. Label them `synthetic`.
- **Tail rotations (partial):** group by TAIL_NUMBER + date, sort by scheduled departure, and keep pairs where destination = next origin (144,746 such pairs). Planned turn = next departure − arrival (both local to X). Where no next delayed leg exists, synthesise one (A3).
- **Taxi times:** per airport-hour TAXI_OUT/TAXI_IN distributions. Note these are from *delayed* flights only, so they may be biased high.
- **Connections:** same airline, arrival then departure at X 35–180 min later. *Plausible* only; both legs must be in the delayed subset, so connections will be undercounted.
- **Seats:** FAA ACFTREF NO-SEATS.

## 3. Real-data enrichment (unchanged)
| Source | URL | Notes |
|---|---|---|
| FAA Releasable Aircraft DB | https://registry.faa.gov/database/ReleasableAircraft.zip (~60 MB) [UNVERIFIED; page 403'd] | MASTER.txt N-NUMBER has no leading "N" (strip before joining). MFR MDL CODE → ACFTREF.txt CODE → MFR, MODEL, NO-ENG, NO-SEATS. No ICAO type or wake field, so hand-map ~40 models (B737/A320 = M; B757 = M in ICAO terms, special in FAA; B767/777/A330 = H; CRJ/ERJ = M). The registry is current; DEREG.txt has retired tails [UNVERIFIED]. Report the match rate. |
| OurAirports runways | https://davidmegginson.github.io/ourairports-data/runways.csv | Join airport_ident = "K" + IATA (contiguous US). Headings, length, closed flag. Current layout. |
| IEM ASOS/METAR archive | https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py (verified) | 3-letter station ID (ORD). E.g. `?station=ORD&data=metar&data=vsby&data=sknt&data=gust&data=wxcodes&year1=2015&month1=1&day1=5&year2=2015&month2=1&day2=6&tz=America/Chicago&format=onlycomma&missing=empty`. 1 request/s; HTTP 429 if exceeded. |
| OSM gates (optional) | Overpass `aeroway=gate` | Label "OSM-derived". |

## 4. Synthetic (one `SEED`, logged; `synthetic: true` on each field) (amended)
- **On-time background traffic (new, see A2):** seeded arrivals at a stated per-hour rate, used only if runway/gate load needs it.
- **Next legs (new, see A3):** where a tail has no next delayed leg, synthesise one with a planned turnaround drawn from the Eurocontrol distribution (median 45 min).
- **Gates:** OSM count if available, else derive one. **Amended:** "peak simultaneous on-ground aircraft × 1.15" now undercounts, because on-time aircraft are missing. Use OSM, or a stated per-airport gate count.
- **Fuel on board:** 14 CFR 121.639 (trip + alternate + 45 min) plus a seeded 0–20 min extra. Holding burn: **25 kg/min for A320/737** (Airbus, primary; see `01-domain-and-constraints.md`); 2,300 kg/h (~38 kg/min) is the sensitivity upper bound; widebody ~6,500 kg/h [rough]. CO2 = 3.16 × fuel.
- **Passengers:** seats × load factor ~0.85 [UNVERIFIED] × hub connecting share 0.3–0.6, spread by a seeded multinomial over plausible connections. Minimum connection time 35–45 min.
- **Ground crew:** seeded rosters (3 shifts, N teams per gate cluster), with team-minutes per turnaround by aircraft size.
- **Weather impact:** the METAR is real; the METAR → acceptance-rate mapping is a stated synthetic rule (e.g. visibility < 3 sm or ceiling < 1,000 ft → 60 → 40 per hour).

## 5. Evaluation plan (unchanged design; notes amended)
- **Sampling:** 2 airport tiers × 2 causes × 8 rows = **N = 32**, fixed seed, 3 LLM runs each (~100 negotiations). 8 held-out scenarios never used for prompt tuning. Both causes are present at the hubs, so stratification still works.
- **Baselines (same scenario input):**
  - B0 do-nothing cascade. **Amended:** propagation uses linked pairs plus synthesised next legs (A3).
  - **B1 greedy first-come-first-served + wake separation + nearest free compatible gate (= the fallback).**
  - B2 CP-SAT optimiser (upper reference).
  - Real downstream delay = context only, linked pairs only (A8).
- **Metrics:**
  - Total, mean and P90 delay minutes
  - Holding fuel (kg) and CO2
  - Missed connections (count and passengers)
  - Violations proposed, caught and leaked (leaked must be 0)
  - Convergence within 3 turns and mean turns
  - Fallback rate
  - Tokens, USD and latency per negotiation
- **Reporting:** paired comparisons; 95% bootstrap CIs for delay differences; Wilson CIs for rates (e.g. 27/32 → [0.68, 0.94]); results by stratum; "N = 32, indicative only"; a provenance table (real / enriched / synthetic). **Amended:** state on the slide that the source data contains only delayed flights.
- **Failure taxonomy:**
  1. Hard-constraint violation
  2. Hallucinated gate, flight or runway
  3. hhmm or midnight arithmetic (including `2400`)
  4. No consensus, or oscillation between proposals
  5. Sycophantic agreement on a plan worse than B1
  6. Ignoring a priority (e.g. low fuel)
  7. Malformed JSON
  8. API timeout → fallback
  9. Objective gaming. **Amended:** cancelling or diverting flights is excluded from the option set (A7).

## 6. Deterministic optimisers (unchanged)
- **Greedy (~1 h):** first-come-first-served + constrained position shifting (max shift 2–3) + a separation matrix. ICAO radar separation in NM: H→H 4, H→M 5, H→L 6, M→L 5. **Amended:** the original said "else 3"; the framing doc adopts 3 NM as a *stated assumption* (ICAO default is 5 NM; see `01-domain-and-constraints.md`). Departures need 2 min for L/M behind H. Gates assigned by earliest-free compatible gate. Runs in milliseconds and is deterministic, so it is the fallback.
- **OR-Tools CP-SAT (2–3 h):** one integer landing time per flight, ≥ its ETA; pairwise ordering booleans with separation enforced via `OnlyEnforceIf`; minimise weighted delay (20–40 flights solve in seconds). Gates: optional intervals, `AddNoOverlap` per gate, `ExactlyOne` per flight. For determinism: `num_search_workers=1`, a fixed `random_seed` and a time limit. https://developers.google.com/optimization/cp/cp_solver

## Caveats
- **The source data contains only delayed flights (pre-filtered by the organisers).**
- Registry and runway data are current, not 2015.
- Delay causes are carrier-attributed, not physical truth.
- Connections are inferred and undercounted.
- Fuel figures are approximate.
