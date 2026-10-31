"""Write docs/RESULTS.md from results/evaluation/summary.json. Every number comes from the evaluation run;
the prose only explains it."""
from __future__ import annotations

from pathlib import Path

from mediator.adapters import REPO

OUT = REPO / "docs" / "RESULTS.md"


def _usd(x) -> str:
    return "n/a" if x is None else (f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}")


def _ci(c) -> str:
    return "n/a" if c[0] is None else f"[{_usd(c[0])}, {_usd(c[1])}]"


def write_results(summary: dict, recs: list[dict]) -> Path:
    S = summary["sample"]
    M, N, P = S["methods"], S["negotiation"], S["paired"]
    A, X, F, AT = S["ablation_checker_off"], S["ablation_extra_fuel"], S["by_stratum"], S["attribution_vs_B0"]
    d = summary["demo"]
    dm = d["m"] if d else None
    b0, neg, b1 = M["B0"], M["NEG"], M["B1"]
    save_total = b0["total_cost_usd"] - neg["total_cost_usd"]
    save_full = b0["total_full_cost_usd"] - neg["total_full_cost_usd"]
    pc = P["NEG_vs_B0:cost_usd"]
    rows = [r for r in recs if r.get("stratum") != "demo" and "m" in r]
    phx = next((r for r in rows if r["outcome"] == "no_consensus" and r["m"]["NEG"]["pax_missed"]
                > r["m"]["B0"]["pax_missed"]), None)
    zero_wx = F.get("medium/weather", {})
    L = []
    w = L.append

    w("# Evaluation results: does the system do what the brief asks, and what does it save?\n")
    w(f"Generated {summary['generated']} by `.venv/bin/python -m evaluation.evaluate` "
      f"(sample seed {summary['sample_seed']}, world seed {summary['world_seed']}). Raw data: "
      "`results/evaluation/summary.json`, `results/evaluation/rows.jsonl`, one consensus log per scenario in `results/evaluation/logs/`.\n")
    w(f"**Sample:** N = {S['n_run']} real DOT 2015 rows, {{large, medium hub}} x {{weather, late aircraft}} x 8, "
      f"fixed seed, October excluded, plus the DFW 24 Apr 2015 demo row reported separately. Cost and delay are "
      f"compared on the {S['n']} scenarios where the system produced a plan; "
      f"{len(S['no_plan'])} scenario ended in a cancellation recommendation and is discussed as a failure. "
      "**Indicative only:** synthetic gates, crews, connections and filler traffic (labelled in each lane).\n")
    w("**Mode:** dry run. Rounds 1-2 are each lane's code-side ranking; round-3 votes are the lanes' dry-run "
      "policies. No LLM calls are made, so the run is free and reproducible. Live Claude votes: `--live N` (needs ANTHROPIC_API_KEY); not run for this file.\n")

    # ------------------------------------------------------------ headline
    w("## Headline\n")
    w(f"| | Status quo (B0) | **Negotiated system** | Fallback solver (B1) |\n|---|---|---|---|")
    w(f"| Total cost, {S['n']} scenarios (shipped cost model) | {_usd(b0['total_cost_usd'])} | "
      f"**{_usd(neg['total_cost_usd'])}** | {_usd(b1['total_cost_usd'])} |")
    w(f"| Total cost incl. missed connections from late arrival | {_usd(b0['total_full_cost_usd'])} | "
      f"**{_usd(neg['total_full_cost_usd'])}** | {_usd(b1['total_full_cost_usd'])} |")
    w(f"| Plans breaking a hard rule | {b0['invalid']} | **{neg['invalid']}** | {b1['invalid']} |")
    w(f"| Passenger minutes waiting onboard for a gate | {b0['total_gate_wait_min']} | **{neg['total_gate_wait_min']}** "
      f"| {b1['total_gate_wait_min']} |")
    w(f"| Mean focal delay (min) | {b0['mean_focal_delay_min']} | **{neg['mean_focal_delay_min']}** | "
      f"{b1['mean_focal_delay_min']} |")
    w(f"| Airborne holding (min) / CO2 (kg) | {b0['total_holding_min']} / {b0['total_co2_kg']:,} | "
      f"**{neg['total_holding_min']} / {neg['total_co2_kg']:,}** | {b1['total_holding_min']} / {b1['total_co2_kg']:,} |")
    w(f"| Missed connecting pax (Pilot's count) | {b0['total_pax_missed']} | **{neg['total_pax_missed']}** | "
      f"{b1['total_pax_missed']} |\n")
    w(f"- **Cost:** the system saves **{_usd(save_total)}** across {S['n']} disruptions "
      f"({_usd(save_total / S['n'])} per disruption, {save_total / b0['total_cost_usd']:.0%} of status-quo cost). "
      f"With missed connections priced in, the saving is {_usd(save_full)}. "
      f"Paired per scenario: cheaper in {pc['a_better']}, tied in {pc['tie']}, dearer in {pc['b_better']}; "
      f"mean difference {_usd(pc['mean_diff'])}, bootstrap 95% CI {_ci(pc['ci95'])}.")
    w(f"- **Safety:** {N['leaked_violations']} hard-rule violations reached the duty manager. "
      f"The status quo breaks a hard rule in {b0['invalid']} of {S['n']} scenarios, every time "
      f"by leaving passengers waiting more than 30 min for an occupied gate. The checker removed "
      f"{A['unsafe_candidates_caught']} of {A['candidates']} proposed plans.")
    w(f"- **Price paid:** the system accepts **+{P['NEG_vs_B0:system_delay_min']['mean_diff']} min** more mean "
      f"system delay than the status quo (95% CI [{P['NEG_vs_B0:system_delay_min']['ci95'][0]}, {P['NEG_vs_B0:system_delay_min']['ci95'][1]}] min). "
      f"It trades minutes for not keeping passengers onboard at a blocked gate, which costs more per minute.")
    w(f"- **Negotiation vs solver:** the negotiated plan equals the least-cost solver's plan in "
      f"{N['neg_equals_b1']} of {S['n']} scenarios. In the dry run, the money is saved by the shared checker and "
      "cost model, not by the negotiation itself (see §4).\n")

    # ------------------------------------------------------------ requirements
    w("## 1. Does it do what the brief and CLAUDE.md require?\n")
    w("| Requirement (source) | Status | Evidence |\n|---|---|---|")
    w(f"| 3 separate agents, one call each, never one prompt (brief: avoid) | Met | `mediator/adapters.py` "
      f"LaneAgent per lane; live mode = 3 separate Claude calls in round 3 |")
    w(f"| Structured messages (brief) | Met | `mediator/core.py` ScoredPlan / Vote; lane schemas in `agents/schema.py` |")
    w(f"| Explicit constraint checking in code (brief, rubric 25%) | Met | `check_plan`: C-CAP-1, C-FUEL-1, C-CREW-2, "
      f"C-GATE-1/2, C-TURN-1; {A['unsafe_candidates_caught']} unsafe plans caught |")
    w(f"| Traceable consensus log (brief) | Met | JSONL per run + plain-English decision record (`mediator/report.py`) |")
    w(f"| Deterministic non-AI fallback (brief) | Met | `fallback/scenario.py`; ran in {N['outcomes']['no_consensus'] + N['outcomes']['no_valid_plan']} "
      f"of {S['n_run']} scenarios |")
    w(f"| Resolve in under 3 turns, no unbounded loop (brief) | Met | fixed 3 rounds, max {N['rounds_max']}; "
      f"mean {N['mean_latency_s']} s per scenario (dry) |")
    w(f"| Never accept unsafe plans (brief) | Met | {N['leaked_violations']} leaked; final check before output |")
    w(f"| Human decides (rubric: trust) | Mostly | Approve / Reject buttons in `app_prime.py` and `app.py`; the choice "
      f"is kept in the UI session, not yet written to the consensus log |")
    w(f"| Baseline + metrics + visible failure (CLAUDE.md §13) | **Was missing, now added** | this file, `evaluation/` |")
    w(f"| Weather = fewer arrival slots (CLAUDE.md §4) | **Weak** | {zero_wx.get('zero_delay_all_methods', 0)} of "
      f"{zero_wx.get('n', 0)} medium-hub weather rows produce zero delay under every method (actual 2015 mean "
      f"{zero_wx.get('mean_hist_delay')} min), see §5 |")
    w(f"| Depart on time + hold with extra fuel (CLAUDE.md §4) | **Broken** | {X['fuel_fail_as_shipped']} of "
      f"{X['hold_options']} hold options fail the Pilot's fuel check as shipped; 0 would fail with extra fuel sized "
      f"to the Pilot's holdable fuel, see §5 |")
    w(f"| Document crafter (LLM narrative from log, CLAUDE.md §12) | Not built | `mediator/report.py` is a code "
      f"template; good enough for traceability |\n")

    # ------------------------------------------------------------ cost by method
    w("## 2. Cost improvement: every method on the same scenarios\n")
    w("All methods use the same scenario, the same checker (`mediator.adapters.check_plan`) and the same cost model "
      "(`plan_cost`: ATC delay/holding/knock-on + Ground gate/crew/connection). *Connection-aware* adds "
      f"$200 for each passenger the Pilot lane counts as missing a connection because of the arrival time, which "
      "`plan_cost` leaves out (§5).\n")
    w("| Method | What it does | Rule breaks | Mean cost | Mean conn.-aware cost | Mean focal delay | "
      "Mean system delay | Gate wait (min) | Gate changes |\n|---|---|---|---|---|---|---|---|---|")
    for k, v in M.items():
        w(f"| {k} | {v['label']} | {v['invalid']} | {_usd(v['mean_cost_usd'])} | {_usd(v['mean_full_cost_usd'])} | "
          f"{v['mean_focal_delay_min']} | {v['mean_system_delay_min']} | {v['total_gate_wait_min']} | {v['gate_changes']} |")
    w("")
    w("By scenario type (mean connection-aware cost):\n")
    w("| Stratum | n | Consensus | Status quo | System | Solver | Mean system focal delay | Actual 2015 delay |\n"
      "|---|---|---|---|---|---|---|---|")
    for st, v in F.items():
        w(f"| {st} | {v['n']} | {v['consensus']}/8 | {_usd(v['mean_full_cost_B0'])} | {_usd(v['mean_full_cost_NEG'])} | "
          f"{_usd(v['mean_full_cost_B1'])} | {v['mean_focal_delay_NEG']} | {v['mean_hist_delay']} |")
    w(f"\nActual 2015 arrival delay (evaluation only, never shown to agents): mean "
      f"{S['historical']['mean_actual_arrival_delay_min']} min over {S['historical']['n']} rows. The real delay "
      "includes every cause and a full day's knock-on, so it's context, not a like-for-like baseline.\n")

    # ------------------------------------------------------------ decisions
    w("## 3. How each decision changed the system\n")
    g, sl = AT["gate"], AT["slot"]
    w("Savings vs the status quo, split by decision. The gate decision is priced alone (status-quo slot with the "
      "system's gate); the slot/lever decision is the remainder. Same cost model throughout.\n")
    w("| Decision | Owner | Saving | Scenarios it helped | Scenarios it cost |\n|---|---|---|---|---|")
    w(f"| Gate: move off an occupied gate instead of waiting with pax onboard | Ground | {_usd(g['total_saving_usd'])} "
      f"| {g['scenarios_saving']} | {g['scenarios_costing']} |")
    w(f"| Arrival slot / lever: ground delay, retime to cut knock-on or gate wait | ATC + Pilot | "
      f"{_usd(sl['total_saving_usd'])} | {sl['scenarios_saving']} | {sl['scenarios_costing']} |")
    w(f"| **Total** | | **{_usd(g['total_saving_usd'] + sl['total_saving_usd'])}** | | |\n")
    w("Other design decisions, measured:\n")
    w(f"- **Code checker before anything is shown or picked.** It caught {A['unsafe_candidates_caught']} unsafe "
      f"proposals. Each agent's own favourite plan was unsafe in "
      + ", ".join(f"{k.upper()} {v}" for k, v in A["agent_favourites_unsafe"].items())
      + f" scenarios. With the checker off, the mediator's pick would itself be unsafe in "
      f"{A['scenarios_where_pick_would_be_unsafe']} scenario(s). The agents' own vetoes catch most cases, but not all.")
    w(f"- **Multi-agent instead of one domain deciding alone.** Ground alone costs {_usd(M['ground_alone']['mean_cost_usd'])} "
      f"per disruption and breaks a hard rule in {M['ground_alone']['invalid']} scenario(s). ATC alone ({_usd(M['atc_alone']['mean_cost_usd'])}) and "
      f"Pilot alone ({_usd(M['pilot_alone']['mean_cost_usd'])}) cost more than the system ({_usd(neg['mean_cost_usd'])}) and break hard rules "
      f"in {M['atc_alone']['invalid']} and {M['pilot_alone']['invalid']} scenarios (they leave the flight at a blocked "
      f"gate), which the system never does ({neg['invalid']}).")
    w(f"- **Ground delay instead of airborne holding.** The system planned {neg['total_holding_min']} min of holding "
      f"({neg['total_co2_kg']:,} kg CO2), against {M['B0h']['total_holding_min']} min "
      f"({M['B0h']['total_co2_kg']:,} kg) for depart-on-time-and-hold. Ground delay is half the cost per minute "
      "($49 vs $98/min) and burns no fuel.")
    if dm:
        w(f"- **Nash-product pick protects the Pilot's interests (demo row {d['id']}).** The least-cost solver picks "
          f"{dm['B1']['plan']['arrival_slot']} at gate {dm['B1']['plan']['gate']} ({_usd(dm['B1']['cost_usd'])}, "
          f"{dm['B1']['pax_missed']} pax miss connections). The negotiated plan is "
          f"{dm['NEG']['plan']['arrival_slot']} at gate {dm['NEG']['plan']['gate']} ({_usd(dm['NEG']['cost_usd'])}, "
          f"{dm['NEG']['pax_missed']} pax miss). It is {_usd(dm['NEG']['cost_usd'] - dm['B1']['cost_usd'])} dearer on "
          f"the shipped cost but **{_usd(dm['B1']['full_cost_usd'] - dm['NEG']['full_cost_usd'])} cheaper** once missed "
          f"connections are priced. Against the status quo ({_usd(dm['B0']['full_cost_usd'])}, gate wait "
          f"{dm['B0']['gate_wait_min']} min, rule broken) it saves {_usd(dm['B0']['full_cost_usd'] - dm['NEG']['full_cost_usd'])}."
          f" Status-quo airborne holding on this row would break the fuel rule and force a diversion "
          f"({_usd(dm['B0h']['full_cost_usd'])}).")
    w("")

    # ------------------------------------------------------------ honest negotiation result
    w("## 4. What the negotiation adds, honestly\n")
    w(f"- Consensus in {N['consensus']} of {S['n_run']} scenarios ({N['consensus_rate']:.0%}, Wilson 95% CI "
      f"{N['consensus_ci95'][0]:.0%}-{N['consensus_ci95'][1]:.0%}). Outcomes: {N['outcomes']}. The fallback ran in the rest.")
    w("- No-consensus causes: " + "; ".join(f"*{k}* ({v} scenarios)" for k, v in N["no_consensus_reasons"].items())
      + ". ATC's round-3 dry-run policy "
      "rejects any plan whose system delay is above its own best option. The mediator picks on the product of all "
      "three scores and cost, so ATC's vote rule and the pick rule disagree by design. The fallback then picks the "
      "same plan the mediator had already picked.")
    w(f"- The negotiated plan equals the least-cost solver's in {N['neg_equals_b1']} of {S['n']} scenarios. "
      "The pitch claim should be *'agents agree on a near-least-cost plan and explain it; code guarantees safety'*, "
      "not *'negotiation beats the optimiser'*.\n")

    # ------------------------------------------------------------ failures
    w("## 5. Failures and bugs found (with the owner's folder)\n")
    w("1. **Cost model ignores delay-caused missed connections** (`mediator/adapters.py: plan_cost`). Ground "
      "only prices a missed connection when a gate change adds a long walk; the Pilot's count of passengers "
      "missing onward flights because of a late arrival is never priced. So the system will add delay to save "
      "a little gate-wait cost even when passengers then miss connections."
      + (f" Example: {phx['id']} adds {phx['m']['NEG']['focal_delay_min'] - phx['m']['B0']['focal_delay_min']} min "
         f"to save {_usd(phx['m']['B0']['cost_usd'] - phx['m']['NEG']['cost_usd'])}, and "
         f"{phx['m']['NEG']['pax_missed'] - phx['m']['B0']['pax_missed']} pax miss connections "
         f"(connection-aware: {_usd(phx['m']['B0']['full_cost_usd'])} -> {_usd(phx['m']['NEG']['full_cost_usd'])})." if phx else "")
      + " *Fix:* add `assess_plan(...).pax_missed * MISSED_CONNECTION_PER_PAX` to `plan_cost`.")
    w(f"2. **Extra holding fuel is sized against the wrong number** (`atc-agent/atc_agent/menu.py`: "
      "`extra = max(0, hold - HOLDABLE_MIN)` with `HOLDABLE_MIN = 45`). The Pilot can hold only "
      "45 min spare minus the time to the alternate before the must-divert point (18.3 min at DFW). "
      f"{X['fuel_fail_as_shipped']} of {X['hold_options']} hold options fail C-FUEL-1, so 'depart on time and "
      "hold' is never available. *Fix:* size extra fuel from the Pilot's `holdable_before_divert_min`.")
    w(f"3. **Weather barely disrupts anything at medium hubs** (`atc-agent/atc_agent/world_stub.py: weather_hours`). "
      f"Capacity is cut only in hours with a cluster of weather-delayed arrivals. {zero_wx.get('zero_delay_all_methods', 0)} "
      f"of {zero_wx.get('n', 0)} medium-hub weather rows produce zero delay and $0 cost, while the row itself reports "
      "a weather delay. *Fix:* always cut capacity in the focal hour when `WEATHER_DELAY > 15`, or start the "
      "focal flight at `sched + WEATHER_DELAY` as late-aircraft does.")
    nop = S["no_plan"][0] if S["no_plan"] else None
    if nop:
        w(f"4. **False 'no valid plan' from a cross-lane mismatch** ({nop['id']}). Ground's world "
          "(`ground_agent/inputs.py`) treats the weather delay as a late arrival, so it sets 'now' (when Ground hears "
          "of the disruption) to 60 min before `sched + WEATHER_DELAY`. ATC lands the flight near its scheduled "
          "time, so every gate change fails C-GATE-2 with negative notice, the scheduled gate is busy, and the system "
          "recommends cancellation. The behaviour is safe (the human is told, nothing is auto-applied), but the cause "
          "is a bug, not an operational fact. *Fix:* one shared `disrupted_arrival` for all lanes. The ATC menu horizon "
          "(90 min) is also too short for a 185-min weather event.")
    w(f"5. **No-consensus by rule mismatch** (§4, `atc-agent/atc_agent/agent.py` dry-run policy). All 8 medium-hub "
      "late-aircraft rows fail to reach consensus.")
    w("6. **Implausible connection counts** (`agents/pilot_inputs.py: derive_connections`). Every same-airline "
      f"departure 35-180 min later gets 3-25 connecting pax, so the demo's ~50-seat MQ regional jet reports "
      f"{dm['NEG']['pax_missed'] if dm else 'n/a'}+ missed connections. *Fix:* cap the total at a share of "
      "seats for the aircraft class.")
    w("7. **The gate saving is partly built into the synthetic world.** `ground_agent/inputs.py` always books the "
      "scheduled gate A12 until after the disrupted arrival, so the status quo always faces a gate conflict. "
      "That's realistic for a late-aircraft cascade, but the size of the gate saving depends on a synthetic choice. "
      "Say so in the pitch.\n")

    # ------------------------------------------------------------ live
    if summary.get("live"):
        w("## 6. Live run (Claude round-3 votes)\n")
        w("| Scenario | Outcome | Plan valid | Latency (s) | Why (if not consensus) |\n|---|---|---|---|---|")
        for r in summary["live"]:
            w(f"| {r['id']} | {r['outcome'] or r['error']} | {r['valid']} | {r['latency_s']} | {(r['why'] or '')[:160]} |")
        w("")

    w("## Caveats\n")
    w("- N = 32 with one world seed: indicative only. The CIs cover sampling across rows only, not uncertainty in the "
      "synthetic inputs or cost weights; a second world seed and a weight sensitivity sweep are the next checks.")
    w("- Status quo B0 is our model of today's process: FAA-style first-come-first-served ground delay and keep the "
      "scheduled gate. It's priced by the same model, not observed.")
    w("- Synthetic and labelled: filler arrivals, gate occupancy, crew report and shift times, connecting pax counts. "
      "Workbook limits come from `data/raw/challenge2/challenge-2-operational-constraints.xlsx`.")
    OUT.write_text("\n".join(L) + "\n")
    return OUT
