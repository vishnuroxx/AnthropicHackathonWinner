"""AutonomousPrime polished demo UI (alternative to app.py; same data, same backend).

Run: .venv/bin/streamlit run app_prime.py
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
    ("2. Each team weighs in", "ATC · Pilot · Ground", "Each team suggests its best plan"),
    ("3. Agree on a plan", "safety-checked", "Unsafe plans removed; settle in 3 rounds or less"),
    ("4. Recommendation", "explained", "A plain-English summary of what and why"),
    ("5. Your call", "duty manager", "You approve or reject"),
]
PULSE_CSS = """<style>
@keyframes ring {0%,100%{box-shadow:0 0 0 0 rgba(29,78,137,.45)} 50%{box-shadow:0 0 0 9px rgba(29,78,137,0)}}
.stepper{display:flex;background:#fff;border:1px solid #e3e9f1;border-radius:16px;padding:18px 12px 14px;
  box-shadow:0 2px 8px #0b25450f;margin-bottom:16px}
.step{flex:1 1 0;min-width:0;text-align:center;position:relative;padding:0 6px}
.step:not(:last-child)::after{content:"";position:absolute;top:17px;left:calc(50% + 22px);right:calc(-50% + 22px);
  height:3px;border-radius:2px;background:#e3e9f1}
.step.done:not(:last-child)::after{background:#2e7d32}
.dot{width:36px;height:36px;border-radius:50%;margin:0 auto 8px;display:flex;align-items:center;justify-content:center;
  font-weight:700;font-size:.95rem;border:2px solid #9aa7b8;color:#56627a;background:#fff}
.stApp .step.done .dot{background:#2e7d32;border-color:#2e7d32;color:#fff}
.stApp .step.active .dot{background:#1d4e89;border-color:#1d4e89;color:#fff;animation:ring 1.4s infinite}
.stApp .step .t{font-weight:600;font-size:.88rem;color:#1b2a41;overflow-wrap:anywhere}
.stApp .step .d{font-size:.75rem;color:#56627a;margin-top:2px;overflow-wrap:anywhere}
.stApp .step.todo .t{color:#56627a}
@media (max-width:700px){.stepper{flex-direction:column;gap:12px}.step{text-align:left;display:flex;gap:10px}
  .step::after{display:none}.dot{margin:0}}
</style>"""


# Renders the 5-stage workflow as a stepper into a placeholder.
# Args: slot - st.empty() placeholder; active - 0-based index of the current stage (5 = all done).
def render_stages(slot, active):
    steps = []
    for i, (title, _who, what) in enumerate(STAGES):
        cls = "done" if i < active else "active" if i == active else "todo"
        mark = "✓" if i < active else str(i + 1)
        steps.append(f'<div class="step {cls}"><div class="dot">{mark}</div><div><div class="t">{title.split(". ", 1)[-1]}</div>'
                     f'<div class="d">{what}</div></div></div>')
    slot.markdown(PULSE_CSS + '<div class="stepper">' + "".join(steps) + "</div>", unsafe_allow_html=True)


# Formats an HHMM string or minutes-from-midnight int as HH:MM.
def hhmm(v):
    if isinstance(v, (int, float)):
        return f"{int(v) // 60 % 24:02d}:{int(v) % 60:02d}"
    s = str(v).zfill(4)
    return f"{s[:2]}:{s[2:]}"


# Reads the scheduled (non-outcome) fields of one demo row from flights.csv.
# Args: spec - a DEMO_ROWS entry.
# Returns: dict of SHOWN_COLS, or None if the row is missing.
@st.cache_data(show_spinner=False)
def load_row(airline, flight_number, origin):
    with open(FLIGHTS, newline="") as f:
        for r in csv.DictReader(f):
            if (r["MONTH"], r["DAY"], r["AIRLINE"], r["FLIGHT_NUMBER"], r["ORIGIN_AIRPORT"]) == (
                    str(MONTH), str(DAY), airline, flight_number, origin):
                return {c: r[c] for c in SHOWN_COLS}
    return None


# Gathers the key constraints (holdable fuel, gate, slot capacity) from the agents' world builders.
# Returns: list of (label, value) pairs; empty if the builders fail.
@st.cache_data(show_spinner=False)
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


ROUND_TITLES = {1: "Round 1: each team suggests a plan", 2: "Round 2: each team rates the options",
                3: "Round 3: final yes/no vote"}
ACTIONS = {"propose": "Suggested", "score": "Rated", "accept": "Agreed", "counter": "Countered",
           "reject": "Rejected"}
TEAM = {"atc": "Air traffic control", "pilot": "Pilot", "ground": "Ground crew"}
TEAM_TAG = {"atc": "ATC", "pilot": "PLT", "ground": "GND"}
# Plain-English meaning of each constraint rule family (rule IDs from docs/challenge-2-framing.md).
RULES = {"C-FUEL": "not enough fuel to hold safely", "C-CREW-1": "ground crew shift would run over",
         "C-CREW-2": "flight crew would exceed legal duty hours", "C-GATE": "no gate free in time",
         "C-SLOT": "no runway slot within capacity", "C-TURN": "turnaround too short", "C-WAKE": "wake separation too tight"}


# Translates a checker violation like "C-CREW-2: flight crew duty margin -104.0 min < 0" into plain English.
# Returns: (rule_id, plain meaning, raw evidence).
def explain_violation(v):
    rule, _, raw = str(v).partition(":")
    meaning = next((m for k, m in RULES.items() if rule.startswith(k)), "breaks a safety rule")
    return rule.strip(), meaning, raw.strip()


# Returns the distinct violations behind every rejected plan in the log, as explain_violation tuples.
def blocking_reasons(log):
    seen, out = set(), []
    for e in log:
        for v in (e.get("checker") or {}).get("violations") or []:
            if v not in seen:
                seen.add(v)
                out.append((e["agent"], *explain_violation(v)))
    return out


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
                check = "Safe" + (f" · ${c['cost']:,.0f}" if isinstance(c.get("cost"), (int, float)) else "")
            else:
                check = "Unsafe: " + "; ".join(str(v).split(":")[0] for v in c.get("violations") or ["invalid"])
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
        act = msg.get("action", "")
        col.markdown(f'<div class="team"><div class="team-h"><span class="badge b-{a}">{TEAM_TAG.get(a, a)}</span>'
                     f'<b>{TEAM.get(a, a)}</b><span class="vote v-{act}">{ACTIONS.get(act, act)}</span></div>'
                     f'<div class="why">{html.escape(msg.get("reason", ""))}</div></div>', unsafe_allow_html=True)


# Writes a short plain-English story of the negotiation from the log only (no new facts).
def plain_explanation(res):
    log, p = res.get("log", []), res.get("final_plan") or {}
    if p:
        out = ["#### What we recommend", f"**{plan_line(p)}**."]
    else:
        out = ["#### What we recommend", "**Cancel this flight.** No plan from any team passed every safety rule:"]
        out += [f"- {TEAM.get(a, a)}'s best plan: {meaning} (`{rule}`: {raw})" for a, rule, meaning, raw in blocking_reasons(log)]
        out.append("Cancellation is never decided by the agents. It is a recommendation for you to confirm or override.")
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
    elif p:
        out.append("The teams did not all agree, so the system picked the cheapest safe plan by rule (no AI).")
    else:
        out.append("Every proposed plan was removed by the safety checker, so there was nothing safe to vote on.")
    last = [e for e in log if e["round"] == max((x["round"] for x in log), default=0)]
    if last:
        out.append("#### Final vote, in each team's words")
        for e in last:
            m = e.get("message") or {}
            out.append(f"- {TEAM.get(e['agent'], e['agent'])} ({ACTIONS.get(m.get('action'), m.get('action', ''))}): {m.get('reason', '')}")
    out.append("#### What is real and what is simulated")
    out.append("Flight times and delays are real 2015 records. Gate bookings, crew shifts and connecting "
               "passengers are simulated for the demo. All numbers are calculated by code, not by the AI.")
    return "\n\n".join(out)


load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")
st.set_page_config(page_title="Flight Disruption Assistant by AutonomousPrime", layout="wide")
# Design tokens: navy ops-room palette; one radius for containers, pills only on small tags.
PAGE_CSS = """<style>
:root{--ink:#14213d;--ink-2:#4a5a73;--navy:#0b2545;--navy-2:#1d4e89;--line:#dfe6ef;--paper:#f6f8fb;
  --ok:#1e7a3c;--ok-bg:#e9f5ec;--warn:#9a5b00;--warn-bg:#fff4e0;--bad:#a8231f;--bad-bg:#fdecea;
  --atc:#1d4e89;--pilot:#6a3d9a;--ground:#b4540a}
.stApp{background:var(--paper);color:var(--ink);color-scheme:light}
[data-testid="stHeader"]{background:var(--paper)}
[data-testid="stMain"] :is(p,li,span,label,h1,h2,h3,h4,h5,h6,div,summary,td,th,strong,b,em,small){color:var(--ink)}
[data-testid="stMain"] [data-testid="stCaptionContainer"] *{color:var(--ink-2)}
[data-testid="stMain"] [data-testid="stExpander"] details,[data-testid="stMain"] [data-testid="stExpander"] summary{background:#fff;border-color:var(--line)}
[data-testid="stMain"] table,[data-testid="stMain"] th,[data-testid="stMain"] td{background:#fff;border-color:var(--line)}
[data-testid="stMain"] code{background:#eef2f7;color:var(--ink)}
[data-testid="stMain"] [data-testid="stMetricDelta"],[data-testid="stMain"] [data-testid="stMetricDelta"] *{color:var(--bad);background:var(--bad-bg)}
[data-testid="stMain"] [data-testid="stMetricDelta"] svg{fill:var(--bad)}
[data-testid="stBaseButton-secondary"]{background:#fff;border-color:#9aa7b8}
[data-testid="stMain"] [data-testid="stBaseButton-primary"] *{color:#fff}
.stApp .hero h1 *,.stApp .hero .by *{color:inherit}
[data-testid="stBaseButton-secondary"] *{color:var(--ink)}
[data-testid="stMain"] [data-testid="stCheckbox"] label,[data-testid="stMain"] [data-testid="stWidgetLabel"] *{color:var(--ink)}
::selection{background:#1d4e8933}
.block-container{max-width:1200px;padding-top:3.5rem}
h1,h2,h3,h4{color:var(--ink);letter-spacing:-.02em;text-wrap:balance}
.stApp .hero{background:var(--navy);color:#fff;padding:22px 28px;border-radius:14px;margin-bottom:16px;
  display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.stApp .hero h1{color:#fff;margin:0;font-size:2rem;padding:0}
.stApp .hero p{color:#c9d8ec;margin:6px 0 0;max-width:62ch}
.stApp .hero .by{color:#c9d8ec;font-size:.85rem;text-align:right}
.hero .by b{color:#fff;font-size:1rem;display:block}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-height:120px;height:100%}
[data-testid="stMetricValue"],[data-testid="stMetricValue"] *{white-space:normal!important;overflow:visible!important;
  text-overflow:clip!important;font-size:1.6rem;line-height:1.2;font-variant-numeric:tabular-nums}
.team{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-height:200px;margin-bottom:18px;overflow-wrap:anywhere}
.team-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.stApp .team-h b{color:var(--ink)}
.stApp .badge{font-size:.7rem;font-weight:700;color:#fff;border-radius:6px;padding:2px 6px;letter-spacing:.02em}
.stApp .b-atc{background:var(--atc)}.stApp .b-pilot{background:var(--pilot)}.stApp .b-ground{background:var(--ground)}
.stApp .vote{margin-left:auto;font-size:.78rem;font-weight:600;border-radius:999px;padding:2px 10px;background:#eef2f7;color:var(--ink-2)}
.stApp .v-accept{background:var(--ok-bg);color:var(--ok)}.stApp .v-reject{background:var(--bad-bg);color:var(--bad)}
.stApp .team .why{color:var(--ink-2);font-size:.85rem;margin-top:10px;line-height:1.45}
.verdict{border-radius:12px;padding:16px 20px;margin:8px 0 14px;border:1px solid}
.stApp .verdict .h{font-size:1.15rem;font-weight:700}
.verdict ul{margin:8px 0 0;padding-left:1.1rem;font-size:.92rem}
.stApp .verdict code{font-size:.8rem;background:#ffffffaa}
.stApp .verdict *{color:inherit}
.stApp .vd-ok{background:var(--ok-bg);border-color:#b7dfc2;color:var(--ok)}
.stApp .vd-warn{background:var(--warn-bg);border-color:#f1d29a;color:var(--warn)}
.stApp .vd-bad{background:var(--bad-bg);border-color:#f3c2be;color:var(--bad)}
.stApp .decision{border-radius:12px;padding:16px 20px;margin:14px 0;color:#fff;animation:pop .3s cubic-bezier(.16,1,.3,1)}
.stApp .decision .h{font-size:1.2rem;font-weight:700}.stApp .decision .s{color:#ffffffdd;font-size:.9rem;margin-top:2px}
.stApp .d-ok{background:var(--ok)}.stApp .d-no{background:var(--bad)}
@keyframes pop{from{transform:translateY(4px);opacity:0}to{transform:none;opacity:1}}
@media (prefers-reduced-motion:reduce){.decision,.step.active .dot{animation:none!important}}
.lim{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.lim>div{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.stApp .lim .k{font-size:.8rem;color:var(--ink-2);display:flex;justify-content:space-between;gap:8px}
.stApp .lim .v{font-weight:600;color:var(--ink);margin-top:2px;font-variant-numeric:tabular-nums}
.stApp .tag{font-size:.68rem;border-radius:999px;padding:1px 8px;white-space:nowrap}
.stApp .t-sim{background:var(--warn-bg);color:var(--warn)}.stApp .t-real{background:var(--ok-bg);color:var(--ok)}
.evals{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:10px}
.evals>div{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stApp .evals .n{font-size:1.5rem;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}
.stApp .evals .l{font-size:.85rem;color:var(--ink-2)}
[data-testid="stSidebar"]{background:var(--navy)}
[data-testid="stSidebar"] *{color:#e6eef8}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div:has(> input),[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"]>div{background:#fff!important}
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg{fill:var(--ink)!important;color:var(--ink)!important}
[data-testid="stMain"] [data-testid="stCheckbox"] [role="switch"]:not([aria-checked="true"]),[data-testid="stMain"] label:has(input[type="checkbox"]:not(:checked)) > div:first-child{background:#9aa7b8}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] *,[data-testid="stSidebar"] [data-testid="stSelectbox"] input{color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important}
[data-testid="stBaseButton-primary"]{background:var(--navy-2);border-color:var(--navy-2);color:#fff}
[data-testid="stBaseButton-primary"]:hover{background:var(--navy);border-color:var(--navy);color:#fff}
.sb-brand{font-size:1.25rem;font-weight:700;margin-bottom:2px}
.sb-sub{font-size:.8rem;color:#a9c1e0!important;margin-bottom:18px}
.sb-card{border-top:1px solid #ffffff26;padding:12px 0 0;margin-top:14px;font-size:.84rem;line-height:1.55}
.sb-card b{color:#fff}
:focus-visible{outline:2px solid var(--navy-2)!important;outline-offset:2px}
</style>"""
st.markdown(PAGE_CSS + '<div class="hero"><div><h1>Flight Disruption Assistant by AutonomousPrime</h1>'
            '<p>Air traffic control, the pilot and the ground crew negotiate a recovery plan. '
            'Code checks every safety rule. You make the final call.</p></div>'
            '<div class="by">Airbus Challenge 2 · Autonomous SG 2026</div></div>',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sb-brand">AutonomousPrime</div><div class="sb-sub">Duty manager console · DFW · 24 Apr 2015</div>',
                unsafe_allow_html=True)
    row_id = st.selectbox("Disrupted flight", list(DEMO_ROWS), format_func=lambda k: DEMO_ROWS[k]["label"])
    use_cache = st.toggle("Replay saved run", value=True,
                          help="On: replay a saved negotiation instantly. Off: the three Claude agents negotiate live.")
    st.markdown('<div class="sb-card"><b>Who is at the table</b><br>Air traffic control: runway slots<br>'
                'Pilot: fuel, duty hours, diversion<br>Ground crew: gates and staff</div>'
                '<div class="sb-card"><b>Ground rules</b><br>Code checks every safety rule<br>Three rounds at most<br>'
                'No deal: cheapest safe plan, chosen by rule<br>You make the final call</div>', unsafe_allow_html=True)
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
event = f"Weather, +{w:g} min" if w > 15 else f"Late aircraft, +{l:g} min"
c1, c2, c3 = st.columns(3)
c1.metric("Problem", event)
c2.metric("Flight", f"{row['AIRLINE']}{row['FLIGHT_NUMBER']} · {row['TAIL_NUMBER']}")
c3.metric("Route", f"{row['ORIGIN_AIRPORT']} → {row['DESTINATION_AIRPORT']}")
st.write(f"Was due to leave at **{hhmm(row['SCHEDULED_DEPARTURE'])}** and land at **{hhmm(row['SCHEDULED_ARRIVAL'])}** "
         f"on {DAY} Apr 2015 (real flight record).")
with st.expander("Limits we have to respect"):
    cells = []
    with st.spinner("Loading limits…"):
        limits = key_constraints(spec["airline"], spec["flight_number"], spec["origin"])
    for label, val in limits:
        sim = "(synthetic)" in val
        clean = html.escape(val.replace(" (synthetic)", "").replace(" (derived)", "").replace(" (workbook)", ""))
        tag = '<span class="tag t-sim">simulated</span>' if sim else '<span class="tag t-real">real rule</span>'
        cells.append(f'<div><div class="k">{html.escape(label)}{tag}</div><div class="v">{clean}</div></div>')
    st.markdown('<div class="lim">' + "".join(cells) + "</div>", unsafe_allow_html=True)

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
    plan, log = res.get("final_plan"), res.get("log", [])
    if res.get("outcome") == "consensus":
        st.markdown(f'<div class="verdict vd-ok"><div class="h">All three teams agreed in round {res.get("rounds")}. '
                    'Every safety check passed.</div></div>', unsafe_allow_html=True)
    elif plan:
        st.markdown('<div class="verdict vd-warn"><div class="h">No agreement after 3 rounds. The cheapest safe plan '
                    'was chosen by rule, without AI.</div></div>', unsafe_allow_html=True)
    else:
        items = "".join(f"<li><b>{TEAM.get(a, a)}</b>'s best plan: {html.escape(m)} <code>{html.escape(r)}: {html.escape(raw)}</code></li>"
                        for a, r, m, raw in blocking_reasons(log))
        st.markdown('<div class="verdict vd-bad"><div class="h">No safe plan exists. We recommend cancelling this flight.</div>'
                    f'<ul>{items}</ul></div>', unsafe_allow_html=True)
    if plan:
        st.markdown(f"### {plan_line(plan)}")
        render_summary(res, row)
    # Button labels name the action they take; a cancellation is confirmed or overridden, never auto-applied.
    choices = ((("Approve plan", "Approved"), ("Reject plan", "Rejected")) if plan
               else (("Confirm cancellation", "Cancellation confirmed"), ("Override: keep flying", "Overridden")))
    a, b, _ = st.columns([1.3, 1.3, 3])
    for (label, past), col in zip(choices, (a, b)):
        if col.button(label, key=label, type="primary" if col is a else "secondary", width="stretch"):
            st.session_state["approval"] = {"row_id": row_id, "decision": past, "at": datetime.now().isoformat(timespec="seconds")}
            st.session_state["stage"] = 5
            st.toast(f"{past} by the duty manager")
            render_stages(stage_slot, 5)
    if "approval" in st.session_state:
        d = st.session_state["approval"]
        ok = d["decision"] in ("Approved", "Cancellation confirmed")
        when = datetime.fromisoformat(d["at"]).strftime("%H:%M:%S on %d %b %Y")
        detail = {"Approved": "Recovery plan released to ATC, the pilot and the ground crew.",
                  "Rejected": "Plan sent back. No action taken.",
                  "Cancellation confirmed": "Cancellation passed to the airline's rebooking process.",
                  "Overridden": "Cancellation overridden. The flight stays on manual control."}[d["decision"]]
        st.markdown(f'<div class="decision {"d-ok" if ok else "d-no"}"><div class="h">{d["decision"]} by the duty manager</div>'
                    f'<div class="s">{detail} Logged at {when}.</div></div>', unsafe_allow_html=True)

    # 7. Supporting detail, collapsed by default
    with st.expander("Why this plan? (plain-English explanation)", expanded=True):
        st.markdown(plain_explanation(res))
        if st.toggle("Show the technical decision record", key="techdoc"):
            st.markdown(res.get("document") or template_document(res))
    with st.expander("Show every message (audit trail)"):
        render_log(res.get("log", []))

# 8. Evaluation: headline numbers from the batch run, including where the agents do worse.
ev = RESULTS / "eval_summary.json"
if ev.exists():
    with st.expander("How well does it work? (tested on many flights)"):
        data = json.loads(ev.read_text())
        e = data[0] if isinstance(data, list) else data
        if "flights" in e:
            n_cons = e["agents_cost_le_fallback"] + e["agents_cost_gt_fallback"]
            tiles = [(f"{e['unsafe_plans_chosen']}", "unsafe plans chosen"),
                     (f"{e['consensus']} of {e['flights']}", f"flights reached agreement ({e['consensus_pct']:g}%)"),
                     (f"${e['avg_cost_agents_usd']:,.0f}", f"average cost of the agents' plan, vs ${e['avg_cost_fallback_usd']:,.0f} for the rule-based fallback"),
                     (f"{e['no_consensus_or_no_valid_plan']}", "flights handed to the fallback or to you")]
            st.markdown('<div class="evals">' + "".join(f'<div><div class="n">{n}</div><div class="l">{l}</div></div>' for n, l in tiles)
                        + "</div>", unsafe_allow_html=True)
            st.markdown(f"**Where it falls short.** The agents' plan cost more than the fallback's in "
                        f"**{e['agents_cost_gt_fallback']} of {n_cons}** agreed flights. The rule-based fallback stays the cost "
                        f"baseline, and the code safety checker, not the AI, is what keeps every plan safe.")
            st.caption(f"{e['flights']} DFW flights ({e['weather']} weather, {e['late_aircraft']} late aircraft), "
                       f"mode: {e['mode']}, {e['errors']} errors, {e['seconds']} s total.")
        else:
            st.table(data if isinstance(data, list) else [data])
