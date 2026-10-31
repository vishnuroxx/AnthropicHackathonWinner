"""Turn a mediator JSONL log into a plain-English decision record (Markdown) a duty manager can read.

Every statement comes from a log line; nothing is computed or invented here.
"""
import json
from pathlib import Path


def _plan(p: dict) -> str:
    if p.get("divert"):
        return f"divert, gate {p.get('gate')}"
    how = f"{p['ground_delay_min']} min ground delay" if p["ground_delay_min"] else "no ground delay"
    if p["holding_min"]:
        how += f", {p['holding_min']} min holding"
    if p["extra_fuel_min"]:
        how += f", {p['extra_fuel_min']} min extra fuel"
    return f"arrive {p['arrival_slot']} ({how}), gate {p.get('gate')}"


def render(log_path: Path) -> str:
    lines = [json.loads(x) for x in Path(log_path).read_text().splitlines() if x.strip()]
    by = lambda step: [l for l in lines if l["step"] == step]  # noqa: E731
    out = []
    sc = by("scenario")[0] if by("scenario") else {}
    oc = by("outcome")[-1]
    out += [f"# Decision record: {lines[0]['negotiation_id']}", "",
            f"**Outcome: {oc['outcome'].replace('_', ' ').upper()}.** {oc['why']}", ""]
    if oc.get("plan"):
        out += [f"**Plan {oc['plan_id']}:** {_plan(oc['plan'])}.", ""]
    if sc:
        out += ["## Disruption", ""] + [f"- {k}: {v}" for k, v in sc.items()
                                         if k not in ("ts", "negotiation_id", "round", "step", "rules")] + [""]
        out += ["## Rules the mediator applied (code, not AI)", ""] + [f"- {k}: {v}" for k, v in sc["rules"].items()] + [""]

    out += ["## Round 1: each agent proposes up to 10 plans", ""]
    for l in by("proposals"):
        top = l["plans"][0] if l["plans"] else None
        out.append(f"- **{l['agent'].upper()}** sent {len(l['plans'])} plans."
                   + (f" Its favourite: {_plan(top['plan'])}. Why: {top['reason']}" if top else ""))
    f = by("filter")[0]
    out += ["", f"The mediator received {f['received']} plans, merged duplicates into {f['unique']}, "
            f"and the constraint checker (code) kept **{f['valid']}**.", "", "Plans removed by the checker:", ""]
    removed = [l for l in by("check") if not l["valid"]]
    out += [f"- {l['plan_id']} ({', '.join(l['proposed_by'])}): {_plan(l['plan'])}. Broke: {'; '.join(l['violations'])}"
            for l in removed] or ["- none"]

    if by("shortlist"):
        s = by("shortlist")[0]
        out += ["", f"**Shortlist** (each agent's top 3 safe plans): {', '.join(s['plan_ids'])}", ""]
        out += [f"- {pid}: {_plan(v['plan'])}; total cost ${v['cost_usd']:,.0f}; proposed by {', '.join(v['proposed_by'])}"
                for pid, v in s["plans"].items()]

    if by("scores"):
        out += ["", "## Round 2: every agent scores the whole shortlist (1 = best for it)", ""]
        scores = {l["agent"]: l["scores"] for l in by("scores")}
        pick = by("pick")[0]
        out += ["| Plan | ATC | Pilot | Ground | Total cost | Product |", "|---|---|---|---|---|---|"]
        for r in pick["ranking"]:
            s = r["scores"]
            mark = " **(picked)**" if r["plan_id"] == pick["plan_id"] else ""
            out.append(f"| {r['plan_id']}{mark} | {s['atc']} | {s['pilot']} | {s['ground']} | "
                       f"${r['cost_usd']:,.0f} | {r['product']} |")
        out += ["", "Agents' reasons for the picked plan:", ""]
        out += [f"- {a.upper()} ({scores[a][pick['plan_id']][0]}): {scores[a][pick['plan_id']][1]}" for a in scores]
        runner = pick["ranking"][1] if len(pick["ranking"]) > 1 else None
        out += ["", f"**Why {pick['plan_id']}:** highest product of the three agents' scores and the cost score"
                + (f" ({pick['ranking'][0]['product']} vs next best {runner['plan_id']} at {runner['product']})."
                   if runner else ".")]

    if by("votes"):
        v = by("votes")[0]
        out += ["", f"## Round 3: accept or reject {v['plan_id']}", ""]
        out += [f"- **{a.upper()}: {'ACCEPT' if x['accept'] else 'REJECT'}.** {x['reason']}" for a, x in v["votes"].items()]
        fc = by("final_check")
        if fc:
            out += ["", f"Final safety check (code): {'passed' if fc[0]['valid'] else 'FAILED: ' + '; '.join(fc[0]['violations'])}."]

    for fb in by("fallback"):
        d = fb["detail"]
        out += ["", "## Fallback (deterministic, no AI)", "",
                f"Triggered because: **{fb['trigger']}**. The solver enumerated {d['candidates_enumerated']} plans, "
                f"{d['valid']} passed every hard rule; rejections by rule: {d['rejected_by_rule']}.", ""]
        if fb["plan"]:
            out += [f"**Fallback plan ({d['selected_source_id']}):** {_plan(fb['plan'])}; cost ${fb['cost_usd']:,.0f}, "
                    f"total system delay {fb['total_system_delay_min']} min. Rule: cheapest valid plan "
                    f"(tie-break {', '.join(d['tie_break'])})."]
            if d.get("runner_up"):
                r = d["runner_up"]
                out.append(f"Runner-up {r['source_id']}: {_plan(r['plan'])}; cost ${r['cost_usd']:,.0f}.")
        else:
            out += [f"**No valid plan: recommend cancellation to the human** ({d.get('note', '')})."]
        out.append("Note: the fallback uses its own world model (fallback/world.py), so its gates and costs can "
                   "differ from the agents' views.")

    out += ["", "## Human decision", "", "The duty manager approves or rejects this recommendation. "
            "Every line above is in the machine log:", "", f"`{log_path}`", ""]
    return "\n".join(out)


def write_report(log_path: Path) -> Path:
    md = Path(log_path).with_suffix(".md")
    md.write_text(render(log_path), encoding="utf-8")
    return md
