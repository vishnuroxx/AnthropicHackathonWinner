> Copied from ../../spec-agent-contract/ on 2026-10-31; source of truth is there.

# Message schema — contract v0.2 hybrid

Companion to `SPEC.md`. Field tables first, then one JSON example each. Example values are illustrative (focal flight MQ3086 FSM→DFW, 24 Apr 2015; scheduled arrival 19:24) and use the ATC stub's cost model.

## 1. Agent message

One object per agent per round: code-filled envelope plus LLM-filled body. Envelope keys in LLM output are discarded before validation.

### Envelope (filled by code, never by the LLM)

| field | type | filled by | rounds | rule |
|---|---|---|---|---|
| `schema_version` | string | code | all | constant `"0.2-hybrid"` |
| `negotiation_id` | string | code | all | `{DEST}-{YYYYMMDD}-{AIRLINE}{FLIGHT}` of the focal flight, e.g. `DFW-20150424-MQ3086` |
| `message_id` | string | code | all | `{negotiation_id}-r{round}-{agent}`, e.g. `DFW-20150424-MQ3086-r2-atc` |
| `state_revision` | int | code | all | 0 in the MVP (static world state) |
| `ruleset_id` | string | code | all | `"challenge2-workbook-2026-10-31"` |
| `status` | `OK \| ERROR` | code | all | `ERROR` only after one failed re-ask (SPEC CAP-7) |
| `validator_errors` | string[] | code | all | `[]` when `OK`; otherwise the validator's messages |

### Body (filled by the LLM; `CLAUDE.md` §7 fields unchanged)

| field | type | filled by | rounds | rule |
|---|---|---|---|---|
| `from` | `atc \| pilot \| ground` | LLM | all | equals the calling agent |
| `round` | int 1–3 | LLM | all | equals the current round |
| `action` | `propose \| accept \| counter \| reject` | LLM | R1 `propose`; R2 `accept \| counter \| reject`; R3 `accept \| reject` | a counter in R3 is invalid output |
| `plan_id` | string \| null | LLM | all | `propose`/`counter`: the agent's local id (ATC: `O#`). `accept`: the table `P#`, which must match the current table. `reject`: null |
| `plan` | object \| null | LLM | R1 propose; R2–R3 accept, counter; null on `reject` | `accept` echoes the table plan's values |
| `plan.arrival_slot` | string `HH:MM` local | LLM | with `plan` | ATC owns it |
| `plan.ground_delay_min` | int ≥ 0 | LLM | with `plan` | minutes |
| `plan.holding_min` | int ≥ 0 | LLM | with `plan` | checked by `C-FUEL-1` |
| `plan.extra_fuel_min` | int ≥ 0 | LLM | with `plan` | Pilot owns it; raises the `C-FUEL-1` limit |
| `plan.gate` | string \| null | LLM | with `plan` | Ground owns it. ATC leaves null; code fills the current gate in the table plan |
| `plan.divert` | bool | LLM | with `plan` | Pilot only. ATC sends `false`; code fills `false` in the table plan |
| `need` | string | LLM | all | ≤ 20 words |
| `offer` | string | LLM | all | ≤ 20 words |
| `reason` | string | LLM | all | ≤ 30 words; cites a constraint or objective; every number appears in the agent's own facts |
| `flags` | enum[] | LLM | all | subset of `{MINIMUM_FUEL, EMERGENCY_FUEL}`; any other value fails validation |

Flag meanings (supersede `CLAUDE.md` §7's "ATC is told to prioritise"):

- `MINIMUM_FUEL`: no added holding and no later slot than the table plan. Not priority (FAA: minimum fuel is not an emergency).
- `EMERGENCY_FUEL`: landing fuel would breach the 30-min final reserve. Requires the earliest valid slot.

### Round rules

| round | agents send | middleman does |
|---|---|---|
| 1 | `propose` | checks every plan; the cheapest VALID plan becomes table plan P1. No valid plan → halt to fallback |
| 2 | `accept \| counter \| reject` on the table plan | all three accept the same `P#` → consensus. Otherwise the cheapest VALID counter becomes the next `P#`, else the table stays |
| 3 | `accept \| reject` | all three accept the same `P#` → consensus. Otherwise halt → deterministic least-cost fallback |

Invalid plans never reach the table or other agents; the proposer sees its violations in the log. Output that is unparseable or invalid is re-asked once, then logged as `reject` with status `ERROR`.

## 2. Table plan (middleman → agents)

| field | type | filled by | rule |
|---|---|---|---|
| `plan_id` | string | code | `P1`, `P2`, … in order of going on the table |
| `proposed_by` | `atc \| pilot \| ground \| fallback` | code | `fallback` only when no agent's round-1 plan is valid (the deterministic solver then supplies the plan); otherwise the agent that proposed it |
| `source_id` | string | code | the proposer's local id (ATC: `O#`) |
| `plan` | object | code | same fields as the message `plan`; gate and divert filled |
| `check` | object | code | see §3 |
| `cost_usd` | number | code | from the cost model |
| `total_system_delay_min` | number | code | focal plus knock-on delay |

## 3. Check (attached by checker code)

| field | type | rule |
|---|---|---|
| `status` | `VALID \| INVALID \| ERROR` | INVALID if any hard rule FAILs; ERROR if a hard rule is UNKNOWN or the checker errored; VALID otherwise (confirmed by Ryan) |
| `checks[]` | object[] | one entry per evaluated rule |
| `checks[].rule_id` | string | an id from `rule-registry.md` |
| `checks[].result` | `PASS \| FAIL \| UNKNOWN` | soft rules (`C-CREW-1`) may FAIL without setting INVALID |
| `checks[].actual` | number \| null | measured value |
| `checks[].limit` | number \| null | rule limit in force |
| `checks[].unit` | string | `min`, `s` (separation rules; the one labelled exception to the minutes rule), `arrivals_per_hour` (`C-CAP-1`), `count` |
| `violations[]` | string[] | each starts with the rule id, e.g. `C-FUEL-1: holding 50 > limit 45`; empty when VALID |

## 4. Log line (one JSONL line per agent message)

| field | type | rule |
|---|---|---|
| `ts` | string | local ISO time `YYYY-MM-DDTHH:MM:SS` |
| `negotiation_id` | string | equals the envelope's |
| `message_id` | string | equals the envelope's |
| `round` | int | 1–3 |
| `agent` | string | `atc \| pilot \| ground` |
| `message` | object | the full enveloped agent message (§1) |
| `check` | object \| null | check of the plan the message concerns: its own plan for `propose`/`counter`, the table plan for `accept`/`reject`; null if none |
| `cost_usd` | number \| null | cost of that same plan |
| `total_system_delay_min` | number \| null | of that same plan |
| `table_plan_id` | string \| null | the `P#` on the table when the message was written; null in R1 |

## 5. Examples

### Agent message: ATC round 2, accept of P1 (envelope + body)

```json
{
  "schema_version": "0.2-hybrid",
  "negotiation_id": "DFW-20150424-MQ3086",
  "message_id": "DFW-20150424-MQ3086-r2-atc",
  "state_revision": 0,
  "ruleset_id": "challenge2-workbook-2026-10-31",
  "from": "atc",
  "round": 2,
  "action": "accept",
  "plan_id": "P1",
  "plan": {"arrival_slot": "21:53", "ground_delay_min": 149, "holding_min": 0,
           "extra_fuel_min": 0, "gate": null, "divert": false},
  "need": "Ground to confirm a gate for the 21:53 arrival.",
  "offer": "Ground delay only; no holding.",
  "reason": "P1 passes the slot check at 172 min total system delay; no option beats it by 5 min, so I accept the stable plan.",
  "flags": [],
  "status": "OK",
  "validator_errors": []
}
```

The same agent's round-1 body, for the local-id convention (envelope as above with `message_id` ending `-r1-atc`):

```json
{
  "from": "atc", "round": 1, "action": "propose", "plan_id": "O37",
  "plan": {"arrival_slot": "21:53", "ground_delay_min": 149, "holding_min": 0,
           "extra_fuel_min": 0, "gate": null, "divert": false},
  "need": "Ground to confirm a gate for the 21:53 arrival.",
  "offer": "Ground delay only; no holding and no extra fuel.",
  "reason": "O37 passes the slot check at 21:53 with 149 min ground delay and no holding.",
  "flags": []
}
```

### Table plan

```json
{
  "plan_id": "P1",
  "proposed_by": "atc",
  "source_id": "O37",
  "plan": {"arrival_slot": "21:53", "ground_delay_min": 149, "holding_min": 0,
           "extra_fuel_min": 0, "gate": "C14", "divert": false},
  "check": {
    "status": "VALID",
    "checks": [
      {"rule_id": "C-CAP-1",  "result": "PASS", "actual": 45,  "limit": 45, "unit": "arrivals_per_hour"},
      {"rule_id": "C-SEP-1",  "result": "PASS", "actual": 120, "limit": 77, "unit": "s"},
      {"rule_id": "C-FUEL-1", "result": "PASS", "actual": 0,   "limit": 45, "unit": "min"},
      {"rule_id": "C-GATE-1", "result": "PASS", "actual": 0,   "limit": 0,  "unit": "count"}
    ],
    "violations": []
  },
  "cost_usd": 9555,
  "total_system_delay_min": 172
}
```

### Check (INVALID variant; the VALID variant sits inside the table plan above)

```json
{
  "status": "INVALID",
  "checks": [
    {"rule_id": "C-FUEL-1", "result": "FAIL", "actual": 52, "limit": 45, "unit": "min"},
    {"rule_id": "C-CAP-1",  "result": "PASS", "actual": 44, "limit": 45, "unit": "arrivals_per_hour"}
  ],
  "violations": ["C-FUEL-1: holding 52 > limit 45"]
}
```

### Log line (the round-2 accept above; shown wrapped, written as one line)

```json
{
  "ts": "2026-10-31T14:30:12",
  "negotiation_id": "DFW-20150424-MQ3086",
  "message_id": "DFW-20150424-MQ3086-r2-atc",
  "round": 2,
  "agent": "atc",
  "message": {
    "schema_version": "0.2-hybrid", "negotiation_id": "DFW-20150424-MQ3086",
    "message_id": "DFW-20150424-MQ3086-r2-atc", "state_revision": 0,
    "ruleset_id": "challenge2-workbook-2026-10-31",
    "from": "atc", "round": 2, "action": "accept", "plan_id": "P1",
    "plan": {"arrival_slot": "21:53", "ground_delay_min": 149, "holding_min": 0,
             "extra_fuel_min": 0, "gate": null, "divert": false},
    "need": "Ground to confirm a gate for the 21:53 arrival.",
    "offer": "Ground delay only; no holding.",
    "reason": "P1 passes the slot check at 172 min total system delay; no option beats it by 5 min, so I accept the stable plan.",
    "flags": [], "status": "OK", "validator_errors": []
  },
  "check": {
    "status": "VALID",
    "checks": [
      {"rule_id": "C-CAP-1",  "result": "PASS", "actual": 45,  "limit": 45, "unit": "arrivals_per_hour"},
      {"rule_id": "C-SEP-1",  "result": "PASS", "actual": 120, "limit": 77, "unit": "s"},
      {"rule_id": "C-FUEL-1", "result": "PASS", "actual": 0,   "limit": 45, "unit": "min"},
      {"rule_id": "C-GATE-1", "result": "PASS", "actual": 0,   "limit": 0,  "unit": "count"}
    ],
    "violations": []
  },
  "cost_usd": 9555,
  "total_system_delay_min": 172,
  "table_plan_id": "P1"
}
```
