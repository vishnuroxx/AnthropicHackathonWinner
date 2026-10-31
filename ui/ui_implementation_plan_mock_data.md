# Autonomous SG 2026: UI Implementation Plan

## 1. UI Architecture Overview
The frontend is designed to fulfill the 20% "Trust and Traceability" judging criteria by making the multi-agent negotiation transparent and keeping the human duty manager in control.

*   **View 1: Alert Inbox (The Trigger)**
    *   Data table pulling from `flights.csv`.
    *   Filters for `WEATHER_DELAY > 15` or `LATE_AIRCRAFT_DELAY > 20`.
    *   "Initiate Autonomous Resolution" button to lock a row and trigger agents.
*   **View 2: Live Negotiation Arena (The Trace)**
    *   4-column grid: ATC Swimlane | Pilot Swimlane | Ground Swimlane | Validated Table.
    *   Live rendering of Agent Status Cards (`action`, `need`, `offer`, `reason`).
    *   Middleman Validator badges (Green/Red pills for constraint checks and costs).
*   **View 3: Resolution Sign-Off (The Document Crafter)**
    *   Structured narrative (Decision, How Reached, Why, Safety Checks, Cost Breakdown, Assumptions).
    *   Irreversible human action buttons: [Approve Plan] and [Reject & Halt].
    *   Manual "Download JSON Log" export.

## 2. State Management (Pseudocode)
```javascript
// TBC: Flexible state structure for future refinement
let appState = {
  currentView: 'INBOX', // Transitions: INBOX -> NEGOTIATION -> SIGN_OFF
  selectedFlight: null, // Populated from flights.csv row selection
  consensusLog: [],     // Appends structured JSON messages from agents
  checkerResults: [],   // Holds validation flags (e.g., MINIMUM_FUEL, Gate Occupied)
  tablePlanId: null,    // The current lowest-cost valid plan on the table
  finalDocument: null   // The crafted narrative and cost breakdown for sign-off
};
```

## 3. Implementation Checklist

### Phase 1: Architecture & Scaffolding
- [ ] Initialize frontend project environment (Next.js/React or Vanilla JS).
- [ ] Set up global CSS, layout grids, and component library (e.g., Tailwind CSS).
- [ ] Define the global state management container.
- [ ] Load mock data payload to unblock View 2 development.

### Phase 2: View 1 - Alert Inbox
- [ ] Build main data table component.
- [ ] Implement CSV parsing for `flights.csv`.
- [ ] Apply logic filters for weather/late delays.
- [ ] Bind "Initiate Autonomous Resolution" button to state transition.

### Phase 3: View 2 - Live Negotiation Arena
- [ ] Construct 4-column CSS grid.
- [ ] Build `AgentStatusCard` component mapping to JSON schema.
- [ ] Implement conditional rendering for `flags` array (e.g., `MINIMUM_FUEL` warning).
- [ ] Build `MiddlemanValidator` badges for table plan constraints.
- [ ] Implement round-based rendering loop.

### Phase 4: View 3 - Resolution Sign-Off
- [ ] Build summary document container.
- [ ] Implement manual JSON Log download.
- [ ] Design and bind [Approve Plan] and [Reject & Halt] buttons.
- [ ] Add success toast notification for DB save.

### Phase 5: Integration & Polish
- [ ] Wire frontend to Python backend Claude agent loop.
- [ ] Verify streaming latency/animations.
- [ ] QA against judging rubric (Traceability & Evaluation).

---

## 4. Mock Data Payload (3-Round Consensus)
Use this array of agent message objects to populate the UI before the backend is ready. It simulates a scenario where agents converge on a plan involving a 20-minute ground delay and a gate change to avoid a weather penalty.

```json
[
  // ---------------- ROUND 1: Initial Proposals ----------------
  {
    "from": "atc",
    "round": 1,
    "action": "propose",
    "plan_id": "P1",
    "plan": { "arrival_slot": "14:30", "ground_delay_min": 30, "holding_min": 0, "extra_fuel_min": 0, "gate": "C14", "divert": false },
    "need": "Reduce arrival rate due to severe weather window.",
    "offer": "Guaranteed arrival slot if ground delay is taken.",
    "reason": "Maintains required wake separation and avoids airborne holding during storm.",
    "flags": []
  },
  {
    "from": "pilot",
    "round": 1,
    "action": "propose",
    "plan_id": "P2",
    "plan": { "arrival_slot": "14:00", "ground_delay_min": 0, "holding_min": 30, "extra_fuel_min": 30, "gate": "C14", "divert": false },
    "need": "Depart on time to protect passenger connections.",
    "offer": "Will load extra fuel to absorb holding in the air.",
    "reason": "Aircraft is pre-departure; we can load extra fuel now to avoid gate wait.",
    "flags": []
  },
  {
    "from": "ground",
    "round": 1,
    "action": "propose",
    "plan_id": "P3",
    "plan": { "arrival_slot": "14:20", "ground_delay_min": 20, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Clear C14 for incoming widebody.",
    "offer": "Alternative gate B12 available for a slightly delayed arrival.",
    "reason": "Avoids ground crew overtime and gate conflicts on C14.",
    "flags": []
  },

  // Note: Middleman evaluates R1. P3 is cheapest valid plan. Table Plan = P3.

  // ---------------- ROUND 2: Responding to Table Plan P3 ----------------
  {
    "from": "atc",
    "round": 2,
    "action": "counter",
    "plan_id": "P3",
    "plan": { "arrival_slot": "14:25", "ground_delay_min": 25, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Ensure spacing for heavy aircraft landing at 14:20.",
    "offer": "Will accept B12 gate change.",
    "reason": "Need an extra 5 minutes ground delay to meet wake separation requirements.",
    "flags": []
  },
  {
    "from": "pilot",
    "round": 2,
    "action": "accept",
    "plan_id": "P3",
    "plan": { "arrival_slot": "14:20", "ground_delay_min": 20, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Confirm fuel margins for delay.",
    "offer": "Accepting ground delay and gate change.",
    "reason": "20 minute delay is acceptable and preserves minimum fuel limits.",
    "flags": []
  },
  {
    "from": "ground",
    "round": 2,
    "action": "accept",
    "plan_id": "P3",
    "plan": { "arrival_slot": "14:20", "ground_delay_min": 20, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Secure B12 availability.",
    "offer": "Confirming B12 is locked for this flight.",
    "reason": "My own proposed plan is still the most efficient for ground ops.",
    "flags": []
  },

  // Note: Middleman evaluates R2. No consensus. ATC countered with P4. Table Plan = P4.

  // ---------------- ROUND 3: Responding to Table Plan P4 ----------------
  {
    "from": "atc",
    "round": 3,
    "action": "accept",
    "plan_id": "P4",
    "plan": { "arrival_slot": "14:25", "ground_delay_min": 25, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Maintain spacing.",
    "offer": "Finalizing slot at 14:25.",
    "reason": "This fully satisfies system throughput and wake separation.",
    "flags": []
  },
  {
    "from": "pilot",
    "round": 3,
    "action": "accept",
    "plan_id": "P4",
    "plan": { "arrival_slot": "14:25", "ground_delay_min": 25, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Ensure safe departure.",
    "offer": "Accepting additional 5 min ground delay.",
    "reason": "Still within acceptable limits before passenger connection drops.",
    "flags": []
  },
  {
    "from": "ground",
    "round": 3,
    "action": "accept",
    "plan_id": "P4",
    "plan": { "arrival_slot": "14:25", "ground_delay_min": 25, "holding_min": 0, "extra_fuel_min": 0, "gate": "B12", "divert": false },
    "need": "Finalize gate schedule.",
    "offer": "Holding B12 open.",
    "reason": "5 extra minutes does not trigger crew overtime on B12.",
    "flags": []
  }
]
```