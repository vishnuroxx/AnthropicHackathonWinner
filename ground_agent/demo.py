"""Terminal demo of the Ground agent on the real DFW 24 Apr 2015 weather row (AA1480 MCI->DFW).

Stub table plan only: the real ATC/Pilot agents and the middleman belong to other lanes.
Usage: .venv/bin/python -m ground_agent.demo
"""
import asyncio
import json
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from agents.constraints import REPO
from ground_agent.agent import GroundAgent, baseline_plan
from ground_agent.assumptions import ASSUMPTIONS
from ground_agent.checker import check_ground
from ground_agent.cost import cost_ground
from ground_agent.icap import build_icap
from ground_agent.inputs import build_world
from ground_agent.timeutil import min_to_hhmm


# Prints a plan's Ground check and cost, all computed by code.
# Args: title - heading; plan - Plan; state - world state.
# Returns: the GroundCheck.
def show(title, plan, state):
    check = check_ground(plan, state)
    print(f"\n--- {title}: gate {plan.gate}, arrival {plan.arrival_slot}")
    print("valid:", check.valid, "| violations:", [v.rule_id for v in check.violations])
    print("metrics:", json.dumps(check.metrics))
    print("cost:", cost_ground(check))
    return check


# Runs round 1 (propose) and round 2 (respond to a stub table plan) for the Ground agent.
async def main():
    load_dotenv(REPO / ".env.local")
    load_dotenv(REPO / ".env")
    state = build_world()
    print(f"{state.focal_flight} {state.tail} {state.event_type} +{state.event_magnitude_min} min at {state.airport}; "
          f"scheduled {min_to_hhmm(state.scheduled_arrival_min)}, disrupted {min_to_hhmm(state.disrupted_arrival_min)}")
    print("provenance:", json.dumps(state.provenance, indent=2))
    print("Ground assumptions to state in the demo:", json.dumps(ASSUMPTIONS, indent=2))

    icap = build_icap(state)
    print("\nICAP priorities (rank, interest, stake USD):")
    for p in icap["priorities"]["ranked"]:
        print(f"  {p['rank']}. {p['id']} {p['name']}: {p['stake_usd']}")
    print("ICAP notes:", icap["notes"] or "none")
    print("ICAP options:", json.dumps(icap["alternatives"]["options"]))
    print("BATNA:", json.dumps(icap["alternatives"]["batna"]))

    agent = GroundAgent(anthropic.AsyncAnthropic(), log_path=REPO / "logs" / "ground_calls.jsonl")
    msg = await agent.propose(state)
    print("\nROUND 1 message:\n", msg.model_dump_json(by_alias=True, indent=2))
    if msg.plan:
        show("Ground proposal", msg.plan, state)

    table = baseline_plan(state).model_copy(update={"arrival_slot": min_to_hhmm(state.disrupted_arrival_min + 10)})
    check = show("stub table plan P1 (scheduled gate)", table, state)
    reply = await agent.respond(state, 2, "P1", table, check, [{"round": 1, "message": msg.model_dump(by_alias=True)}])
    print("\nROUND 2 message:\n", reply.model_dump_json(by_alias=True, indent=2))
    print("\nLLM calls:", json.dumps(agent.call_log, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
