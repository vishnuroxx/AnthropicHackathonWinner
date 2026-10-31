# Research: implementing Challenge #2 with Claude

Research-agent report, checked against live Anthropic docs on 31 Oct 2026. Items under "Not fully verified" need a quick check.

## Amendments
No changes. Nothing in this report depended on the dataset. The cost estimates assume ~4k input tokens per call; a scenario bank of up to ~58 delayed arrivals (the densest hour in the provided data) may push the shared scenario context higher. Measure with `messages.count_tokens` and cap the bank (e.g. the 20–30 flights nearest the disruption) if needed.

## Bottom line
Plain Messages API calls driven by a **deterministic Python orchestrator** (FastAPI). The design is a fixed workflow (3 roles, ≤3 rounds, code veto, code fallback), not an open-ended agent — matches Anthropic's "find the simplest solution possible" and gives judges a clean LLM / non-LLM split: Claude proposes; Python decides, vetoes, logs, falls back.

## Recipe
- **SDK/models:** Python `anthropic`, `client.messages.create`. `claude-haiku-5-5` for all agents in dev and evals; `claude-sonnet-5-5` for the live demo (or Haiku throughout if good enough). No Opus needed.
- **Structured messages (recommended — JSON outputs):** `client.messages.parse(..., output_format=PydanticModel)` → sends `output_config: {"format": {"type": "json_schema", "schema": {...}}}`, returns `response.parsed_output`. One schema per message type, e.g. `{agent, turn, proposal{action, runway, slot, gate, delay_min}, accepts_prior, objections[], rationale_short}`.
- **Alternative — strict tool:** one tool per agent (e.g. `submit_proposal`), `"strict": true` at top level of the tool definition, `"additionalProperties": false` on every object + `required`; `tool_choice: {"type": "auto"}` and instruct the agent to call it.
- **Don't rely on forced `tool_choice`:** `{"type":"tool"}` / `{"type":"any"}` → 400 on Opus 5.5 and Sonnet 5.5; works on Haiku 5.5 but skips thinking.
- **Thinking:** adaptive by default on 5.5; control with `output_config: {"effort": "low" | "medium"}`. No `budget_tokens` (400). `thinking: {"type":"disabled"}` → 400 on Opus/Sonnet 5.5 (Sonnet's off-switch is `{"type":"between_tools"}`). `thinking: {"type":"adaptive","display":"summarized"}` gives readable summaries for the trace UI. Thinking billed as output.
- **Prompt caching:** order is tools → system → messages. System block 1 = shared scenario context with `cache_control: {"type":"ephemeral"}`; block 2 = role prompt with its own `cache_control` → scenario prefix shared across all 3 agents. No timestamps/run IDs in cached prefix. Check `usage.cache_read_input_tokens > 0`. 5-min TTL for live; `"ttl": "1h"` for batches. Minimum cacheable prefix 512 tokens.
- **Orchestrator loop (≤3 rounds):** fan out with `asyncio.gather` on `AsyncAnthropic` → Pydantic-validate → deterministic checker (veto + rule ID) → feed back others' messages + veto reasons → consensus detected in code → else deterministic fallback → append every step to JSONL log.
- **Log per call:** request id, model, prompt hash, parsed message, checker verdict, rule IDs, `usage`.
- **Every call:** check `stop_reason`; `refusal` / `max_tokens` → fallback. `max_tokens` ~2000–4000 (thinking counts).

## Prices (USD / million tokens, live pricing page)
| Model | ID | Input | 5m write | 1h write | Cache read | Output | Batch in/out |
|---|---|---|---|---|---|---|---|
| Opus 5.5 | `claude-opus-5-5` | 4.00 | 5.00 | 8.00 | 0.20 | 20.00 | 2 / 10 |
| Sonnet 5.5 | `claude-sonnet-5-5` | 2.00 | 2.50 | 4.00 | 0.10 | 10.00 | 1 / 5 |
| Haiku 5.5 (≤100k prompt) | `claude-haiku-5-5` | 0.10 | 0.125 | 0.20 | 0.01 | 0.50 | 0.05 / 0.25 |

## Cost estimate (9 calls/scenario, 4k in / 600 out per call)
| | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| 1 live demo run | $0.006 | $0.13 | $0.25 |
| 200-scenario eval, plain | $1.26 | $25.20 | $50.40 |
| + caching | ~$0.98 | ~$19.30 | — |
| + batches | $0.63 | $12.60 | $25.20 |
| + batches + caching | ~$0.50 | ~$9.60 | — |
Budget 1.5–2× output for thinking.

## Batches vs concurrency
Batches: 50% off, stacks with caching, up to 24 h, results unordered (`custom_id`). But negotiation is sequential → 3 sequential batches. **Use `asyncio` + semaphore (5–10 in flight) on Haiku** (~$1.26, minutes). Mention batches as the production path.

## Other Anthropic surfaces
- "Building effective agents": closest pattern is **evaluator-optimizer with a deterministic evaluator** (the checker). Orchestrator-workers doesn't fit (fixed subtasks).
- Multi-agent research post: ~15× tokens → keep exchanges short, structured, capped.
- Agent SDK, Tool Runner, Managed Agents: not a fit (overkill / hides the orchestration judges should see).
- Citations: skip (400 with `output_config.format`). Use our own `rule_refs` / `evidence_ids` fields pointing at scenario IDs; checker verifies they exist.

## Gotchas
- Forced `tool_choice` 400s on Opus/Sonnet 5.5; with manual `thinking: enabled` always errors.
- Assistant prefill → 400 on current models; incompatible with JSON outputs.
- Schema: no `minimum`/`maximum`/`minLength`/`maxLength`, no recursion, `minItems` only 0/1 → enforce ranges in Python. ≤20 strict tools, ≤24 optional params, ≤16 union params per request.
- First call with a new schema is slow (grammar compile, cached 24 h) → warm up before the demo.
- Enum casing not guaranteed → compare case-insensitively.
- Asking for "step-by-step reasoning" in a field can trigger a `reasoning_extraction` refusal → ask for a short rationale.
- Cache invalidated by changing `effort`/thinking config, `output_config.format`, or `tool_choice` (messages) → keep fixed per run.
- Parse tool inputs with `json.loads`.

## Sources
Pricing https://platform.claude.com/docs/en/about-claude/pricing · Models https://platform.claude.com/docs/en/about-claude/models/overview · Structured outputs https://platform.claude.com/docs/en/build-with-claude/structured-outputs · Strict tools https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use · tool_choice https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools · Adaptive thinking https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking · Effort https://platform.claude.com/docs/en/build-with-claude/effort · Caching https://platform.claude.com/docs/en/build-with-claude/prompt-caching · Batches https://platform.claude.com/docs/en/build-with-claude/batch-processing · Citations https://platform.claude.com/docs/en/build-with-claude/citations · Building effective agents https://www.anthropic.com/engineering/building-effective-agents · Multi-agent research https://www.anthropic.com/engineering/multi-agent-research-system · Agent SDK https://code.claude.com/docs/en/agent-sdk

## Not fully verified
Haiku 5.5 thinking-disable rule (use `effort: low`); exact combined caching+batch multiplier; per-call token counts (measure with `messages.count_tokens` / `usage`); Citations page not fetched directly.
