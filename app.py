"""Streamlit demo: ATC · Pilot · Ground disruption negotiation (presentation layer only).

Run: .venv/bin/streamlit run app.py
Reads results/<row_id>.json (written by make_cache.py or a live negotiate() call).
Result keys read: outcome ("consensus" | "halt_least_cost"), rounds, final_plan, log[],
optional document (str) and world (dict). Each log entry: round, agent, message{action,
plan_id, plan, need, offer, reason, flags}, checker{valid, violations, cost}, table_plan_id.
"""
import csv
import html
import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from demo_rows import DAY, DEMO_ROWS, MONTH, SEED

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
FLIGHTS = ROOT / "data/raw/dot2015/flights.csv"
SHOWN_COLS = ["AIRLINE", "FLIGHT_NUMBER", "TAIL_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
              "SCHEDULED_DEPARTURE", "SCHEDULED_ARRIVAL", "SCHEDULED_TIME", "DISTANCE",
              "WEATHER_DELAY", "LATE_AIRCRAFT_DELAY"]  # no outcome columns, ever


# Workflow from CLAUDE.md §5: (title, who, what happens)
STAGES = [
    ("1. Disruption", "real 2015 flight", "A delayed flight comes in"),
    ("2. Each team weighs in", "ATC · Pilot · Ground", "Each team suggests what works best for them"),
    ("3. Agree on a plan", "safety-checked", "Unsafe plans are thrown out; the teams settle on one in 3 rounds or less"),
    ("4. Recommendation", "explained", "A plain-English summary of what and why"),
    ("5. Your call", "duty manager", "You approve or reject"),
]
PULSE_CSS = """<style>
@keyframes pulse {0%,100%{box-shadow:0 0 0 0 rgba(255,170,0,.6)} 50%{box-shadow:0 0 0 8px rgba(255,170,0,0)}}
.stApp{background:linear-gradient(180deg,#eef4fb 0%,#f8fafc 40%,#ffffff 100%)}
[data-testid="stExpander"]{background:#fff;border-radius:12px}
.st-box{flex:1 1 0;min-width:0;padding:10px 12px;border-radius:12px;border:1px solid #d6dee8;background:#fff;
  font-size:.85rem;line-height:1.3;overflow-wrap:anywhere;box-shadow:0 1px 3px #0001}
.st-box b{display:block;margin-bottom:2px}
.st-done{background:#e8f5e9;border-color:#66bb6a}
.st-active{background:#fff8e1;border-color:#ffa000;animation:pulse 1.2s infinite}
.st-todo{opacity:.55}
</style>"""


# Renders the 5-stage workflow bar into a placeholder.
# Args: slot - st.empty() placeholder; active - 0-based index of the current stage (5 = all done).
def render_stages(slot, active):
    boxes = []
    for i, (title, who, what) in enumerate(STAGES):
        cls = "st-done" if i < active else "st-active" if i == active else "st-todo"
        mark = "✓ " if i < active else ""
        boxes.append(f'<div class="st-box {cls}"><b>{mark}{title}</b><br><i>{who}</i><br>'
                     f'<span style="font-size:.75rem">{what}</span></div>')
    slot.markdown(PULSE_CSS + '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">' + "".join(boxes) + "</div>",
                  unsafe_allow_html=True)


# Formats an HHMM string or minutes-from-midnight int as HH:MM.
def hhmm(v):
    if isinstance(v, (int, float)):
        return f"{int(v) // 60 % 24:02d}:{int(v) % 60:02d}"
    s = str(v).zfill(4)
    return f"{s[:2]}:{s[2:]}"


# Reads the scheduled (non-outcome) fields of one demo row from flights.csv.
# Args: spec - a DEMO_ROWS entry.
# Returns: dict of SHOWN_COLS, or None if the row is missing.
@st.cache_data
def load_row(airline, flight_number, origin):
    with open(FLIGHTS, newline="") as f:
        for r in csv.DictReader(f):
            if (r["MONTH"], r["DAY"], r["AIRLINE"], r["FLIGHT_NUMBER"], r["ORIGIN_AIRPORT"]) == (
                    str(MONTH), str(DAY), airline, flight_number, origin):
                return {c: r[c] for c in SHOWN_COLS}
    return None


# Gathers the key constraints (holdable fuel, gate, slot capacity) from the agents' world builders.
# Returns: list of (label, value) pairs; empty if the builders fail.
@st.cache_data
def key_constraints(airline, flight_number, origin):
    try:
        from agents.constraints import fuel_crew_rules
        from agents.pilot import fuel_budget
        from agents.pilot_inputs import build_pilot_inputs
        from ground_agent.inputs import build_world
        w = build_world(airline, flight_number, MONTH, DAY, origin, SEED)
        raw = load_row(airline, flight_number, origin)
        fuel = fuel_budget(build_pilot_inputs({**raw, "MONTH": str(MONTH), "DAY": str(DAY), "YEAR": "2015"}, SEED),
                           fuel_crew_rules())
        free = [g for g, ws in w.gate_busy.items() if not ws]
        return [
            ("Holdable fuel before divert", f"{fuel.holdable_before_divert_min:g} min (derived)"),
            ("Scheduled gate", f"{w.scheduled_gate} (synthetic) — busy until {hhmm(w.gate_busy[w.scheduled_gate][-1].end)} (synthetic)"),
            ("Free gates now", f"{', '.join(free) or 'none'} (synthetic)"),
            ("Slot capacity", f"{w.limits.max_runway_ops_per_hour} runway ops/hour, {w.limits.active_runways} runways (workbook)"),
            ("Connecting pax", f"{w.connecting_pax} (synthetic)"),
            ("Ground crew shift ends", f"{hhmm(w.crew_shift_end_min)} (synthetic)"),
        ]
    except Exception as e:
        return [("Constraints unavailable", repr(e))]


# Loads a cached result for a row, or None.
def load_result(row_id):
    p = RESULTS / f"{row_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


# Runs negotiate() live and saves the result to results/<row_id>.json.
def run_live(row_id):
    from make_cache import cache_one
    from middleman import negotiate
    return cache_one(row_id, negotiate)


# Renders a plan dict as a one-line summary.
def plan_str(p):
    if not p:
        return "—"
    return ", ".join(f"{k}={v}" for k, v in p.items() if v not in (None, "", 0, False)) or "no change"


# Renders a plan dict as a short human line, e.g. "arrive 21:09 · 105 min ground delay · gate B20".
def plan_line(p):
    if not p:
        return "—"
    if p.get("divert"):
        return "divert to alternate"
    bits = [f"arrive {p.get('arrival_slot', '?')}"]
    if p.get("ground_delay_min"):
        bits.append(f"{p['ground_delay_min']} min ground delay")
    if p.get("holding_min"):
        bits.append(f"{p['holding_min']} min holding")
    if p.get("extra_fuel_min"):
        bits.append(f"{p['extra_fuel_min']} min extra fuel")
    if p.get("gate"):
        bits.append(f"gate {p['gate']}")
    return " · ".join(bits)


ROUND_TITLES = {1: "Round 1 — each team suggests a plan", 2: "Round 2 — each team rates the options",
                3: "Round 3 — final yes/no vote"}
ACTIONS = {"propose": "Suggested", "score": "Rated", "accept": "✅ Agreed", "counter": "↩️ Countered",
           "reject": "❌ Rejected"}
TEAM = {"atc": "🗼 Air traffic control", "pilot": "👨‍✈️ Pilot", "ground": "🧳 Ground crew"}


# Renders the negotiation log as one compact table per round (agent, action, plan, safety check, reason).
def render_log(log):
    for rnd in sorted({e["round"] for e in log}):
        st.markdown(f"**{ROUND_TITLES.get(rnd, f'Round {rnd}')}**")
        rows = []
        for e in (e for e in log if e["round"] == rnd):
            m, c = e.get("message") or {}, e.get("checker") or {}
            if not c:
                check = "—"
            elif c.get("valid"):
                check = "✅ yes" + (f" · ${c['cost']:,.0f}" if isinstance(c.get("cost"), (int, float)) else "")
            else:
                check = "❌ " + "; ".join(str(v).split(":")[0] for v in c.get("violations") or ["invalid"])
            rows.append({"Team": TEAM.get(e["agent"], e["agent"]), "Did": ACTIONS.get(m.get("action"), m.get("action", "?")),
                         "Plan": (f"{m['plan_id']}: " if m.get("plan_id") else "") + plan_line(m.get("plan")),
                         "Safe?": check, "Why": m.get("reason", "")})
        st.table(rows)


# Builds the decision document from the log only (used when the result has no crafted document).
def template_document(res):
    log, rounds = res.get("log", []), res.get("rounds")
    how = (f"Consensus in {rounds} round(s)." if res.get("outcome") == "consensus"
           else "No consensus; least-cost valid plan chosen by the deterministic fallback (non-AI).")
    lines = ["### Decision", f"Final plan: {plan_str(res.get('final_plan'))}", "### How reached", how, "### Why"]
    last = {}
    for e in log:
        last[e["agent"]] = e
    for a, e in last.items():
        lines.append(f"- **{a.upper()}** ({(e.get('message') or {}).get('action', '?')}): “{(e.get('message') or {}).get('reason', '—')}”")
    lines.append("### Checker results")
    for e in log:
        c = e.get("checker") or {}
        if c:
            lines.append(f"- R{e['round']} {e['agent'].upper()}: {'valid' if c.get('valid') else 'INVALID ' + str(c.get('violations'))}"
                         + (f", cost ${c['cost']:,.0f}" if isinstance(c.get("cost"), (int, float)) else ""))
    return "\n\n".join(lines)


# Shows the plan's impact (delay vs schedule, cost) and each team's final word, in plain language.
def render_summary(res, row):
    p, log = res.get("final_plan") or {}, res.get("log", [])
    c = next((e.get("checker") for e in reversed(log) if (e.get("checker") or {}).get("cost") is not None), {}) or {}
    m1, m2, m3 = st.columns(3)
    slot = p.get("arrival_slot")
    if slot and not p.get("divert"):
        sched = int(str(row["SCHEDULED_ARRIVAL"]).zfill(4)[:2]) * 60 + int(str(row["SCHEDULED_ARRIVAL"]).zfill(4)[2:])
        h, mm = map(int, slot.split(":"))
        m1.metric("Lands", slot, f"{h * 60 + mm - sched} min late", delta_color="inverse")
    m2.metric("Gate", p.get("gate") or "—")
    if isinstance(c.get("cost"), (int, float)):
        m3.metric("Estimated cost", f"${c['cost']:,.0f}")
    last = {}
    for e in log:
        last[e["agent"]] = e
    cols = st.columns(max(len(last), 1))
    for col, (a, e) in zip(cols, last.items()):
        msg = e.get("message") or {}
        color = {"atc": "#1d4e89", "pilot": "#7b1fa2", "ground": "#ef6c00"}.get(a, "#888")
        col.markdown(f'<div class="team" style="--c:{color}"><b>{TEAM.get(a, a)}</b><br>'
                     f'{ACTIONS.get(msg.get("action"), msg.get("action", ""))}'
                     f'<div class="why">{html.escape(msg.get("reason", ""))}</div></div>', unsafe_allow_html=True)


# Writes a short plain-English story of the negotiation from the log only (no new facts).
def plain_explanation(res):
    log, p = res.get("log", []), res.get("final_plan") or {}
    out = ["#### What we recommend", f"**{plan_line(p)}**."]
    first = [e for e in log if e["round"] == 1]
    if first:
        out.append("#### What each team wanted first")
        for e in first:
            out.append(f"- {TEAM.get(e['agent'], e['agent'])}: {plan_line((e.get('message') or {}).get('plan'))}")
    scored = [e for e in log if e["round"] == 2]
    if scored:
        out.append("#### How each team rated this plan (1 = their ideal)")
        for e in scored:
            r = (e.get("message") or {}).get("reason", "")
            score, _, why = r.partition(":") if r.startswith("scored") else ("", "", r)
            out.append(f"- {TEAM.get(e['agent'], e['agent'])} ({score.replace('scored', '').split(' for')[0].strip() or '?'}): {why.strip()}")
    removed = {v for e in log for v in ((e.get("checker") or {}).get("violations") or [])}
    out.append("#### How they settled")
    out.append("Any plan that broke a safety rule (fuel, gate, runway slots, crew hours) was thrown out "
               "automatically, so no team ever saw an unsafe option. Each team then rated the safe options, "
               "and the plan with the best balance for all three, at a reasonable cost, went to a final vote.")
    if res.get("outcome") == "consensus":
        out.append(f"All three teams said **yes** in round {res.get('rounds')}, and a final safety check passed.")
    else:
        out.append("The teams did not all agree, so the system picked the cheapest safe plan by rule (no AI).")
    last = [e for e in log if e["round"] == max((x["round"] for x in log), default=0)]
    if last:
        out.append("#### Final vote, in each team's words")
        for e in last:
            m = e.get("message") or {}
            out.append(f"- {TEAM.get(e['agent'], e['agent'])} ({ACTIONS.get(m.get('action'), m.get('action', ''))}): {m.get('reason', '')}")
    out.append("#### Good to know")
    out.append("Flight times and delays are real 2015 records. Gate bookings, crew shifts and connecting "
               "passengers are simulated for the demo. All numbers are calculated by code, not by the AI.")
    return "\n\n".join(out)


load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")
st.set_page_config(page_title="ATC · Pilot · Ground", layout="wide")
st.markdown('<style>\n.block-container{max-width:1200px;padding-top:2rem}\n.hero{background:linear-gradient(120deg,#0b2545,#13315c 55%,#1d4e89);color:#fff;padding:22px 28px;border-radius:16px;margin-bottom:16px;box-shadow:0 6px 20px #0b254533}\n.hero h1{color:#fff;margin:0;font-size:2rem}\n.hero p{color:#cfe0f5;margin:6px 0 0}\n[data-testid="stMetric"]{background:#fff;border:1px solid #e3e9f1;border-radius:12px;padding:12px 16px;box-shadow:0 1px 4px #0001}\n.team{background:#fff;border:1px solid #e3e9f1;border-left:5px solid var(--c);border-radius:12px;padding:12px 14px;min-height:120px;box-shadow:0 1px 4px #0001;overflow-wrap:anywhere}\n[data-testid="stMetric"]{min-height:150px;height:100%}[data-testid="stMetricValue"],[data-testid="stMetricValue"] *{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;font-size:1.6rem;line-height:1.2}.team{min-height:250px;height:100%}.team b{font-size:1rem}.team .why{color:#556;font-size:.85rem;margin-top:6px}\n</style>' + '<div class="hero"><h1>✈️ Flight Disruption Assistant</h1><p>Air traffic control, the pilot and the ground crew agree on a recovery plan. You make the final call.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    row_id = st.selectbox("Pick a disrupted flight", list(DEMO_ROWS), format_func=lambda k: DEMO_ROWS[k]["label"])
    use_cache = st.toggle("Instant replay (saved run)", value=True)
spec = DEMO_ROWS[row_id]
if st.session_state.get("row_id") != row_id:
    st.session_state.update(row_id=row_id, stage=0)
    st.session_state.pop("result", None)
    st.session_state.pop("approval", None)
stage_slot = st.empty()
render_stages(stage_slot, st.session_state["stage"])

# 3. Disruption panel
row = load_row(spec["airline"], spec["flight_number"], spec["origin"])
st.subheader("What happened")
if row is None:
    st.error("Row not found in flights.csv")
    st.stop()
w, l = float(row["WEATHER_DELAY"] or 0), float(row["LATE_AIRCRAFT_DELAY"] or 0)
event = f"Bad weather · {w:g} min late" if w > 15 else f"Plane arrived late · {l:g} min"
c1, c2, c3 = st.columns(3)
c1.metric("Problem", event)
c2.metric("Flight", f"{row['AIRLINE']}{row['FLIGHT_NUMBER']} · {row['TAIL_NUMBER']}")
c3.metric("Route", f"{row['ORIGIN_AIRPORT']} → {row['DESTINATION_AIRPORT']}")
st.write(f"Was due to leave at **{hhmm(row['SCHEDULED_DEPARTURE'])}** and land at **{hhmm(row['SCHEDULED_ARRIVAL'])}** "
         f"on {DAY} Apr 2015 (real flight record).")
with st.expander("Limits we have to respect"):
    for label, val in key_constraints(spec["airline"], spec["flight_number"], spec["origin"]):
        st.write(f"- **{label}:** {val}")

# 4. Run
if st.button("Find a recovery plan", type="primary"):
    try:
        render_stages(stage_slot, 1)  # parallel analysis
        if use_cache:
            time.sleep(1.0)
            res = load_result(row_id)
            if res is None:
                st.error(f"No cached result for {row_id}. Run `python make_cache.py`, or turn off the cache toggle.")
            else:
                render_stages(stage_slot, 2)  # negotiation
                time.sleep(1.0)
        else:
            with st.spinner("The three teams are talking it through…"):
                res = run_live(row_id)
        if res:
            st.session_state.update(result=res, stage=3)
            st.session_state.pop("approval", None)
    except ImportError as e:
        st.error(f"Negotiation backend not available: {e}")
    except Exception as e:
        st.error(f"Negotiation failed: {e!r}")
    render_stages(stage_slot, st.session_state["stage"])

res = st.session_state.get("result")
if res and res.get("row_id") == row_id:
    # 6. Outcome first: what was decided, then the human decision, then the supporting detail.
    st.subheader("Recommended plan")
    if res.get("outcome") == "consensus":
        st.success(f"✅ All three teams agreed (after {res.get('rounds')} rounds). Every safety check passed.")
    elif res.get("final_plan"):
        st.warning("The teams did not agree, so the system picked the cheapest safe plan automatically.")
    else:
        st.error("No safe plan exists. The system suggests cancelling this flight. Your decision.")
    if res.get("final_plan"):
        st.markdown(f"### {plan_line(res.get('final_plan'))}")
        render_summary(res, row)
    a, b, _ = st.columns([1, 1, 4])
    for label, past, col in (("Approve", "Approved", a), ("Reject", "Rejected", b)):
        if col.button(label, key=label, type="primary" if label == "Approve" else "secondary", width="stretch"):
            st.session_state["approval"] = {"row_id": row_id, "decision": past, "at": datetime.now().isoformat(timespec="seconds")}
            st.session_state["stage"] = 5
            render_stages(stage_slot, 5)
    if "approval" in st.session_state:
        d = st.session_state["approval"]
        st.info(f"{d['decision']} at {d['at']}")

    # 7. Supporting detail, collapsed by default
    with st.expander("Why this plan? (plain-English explanation)", expanded=True):
        st.markdown(plain_explanation(res))
        if st.toggle("Show the technical decision record", key="techdoc"):
            st.markdown(res.get("document") or template_document(res))
    with st.expander("Show every message (audit trail)"):
        render_log(res.get("log", []))

# 8. Evaluation
ev = RESULTS / "eval_summary.json"
if ev.exists():
    with st.expander("How well does it work? (tested on many flights)"):
        data = json.loads(ev.read_text())
        st.table(data if isinstance(data, list) else [data])
