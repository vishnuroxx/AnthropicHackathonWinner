# Autonomous SG 2026 — team project

Six-hour hackathon build (Sat 31 Oct 2026). Goal: one agent that visibly completes a real, multi-step Singapore task end to end, with a human approval step and a tangible output (report, filled form, drafted email). Optimise for a working demo, not production quality.

## Problem
Airbus track, Challenge #2 (multi-agent disruption negotiation). **Read `docs/challenge-2-brief.md` (brief + rubric) and `docs/challenge-2-framing.md` (design) before building.** Research behind it: `docs/research/`.
User: airline OCC duty manager at a US hub. Three separate Claude agents (ATC, Pilot, Ground) negotiate over code-generated, code-checked recovery options for a real DOT 2015 disruption; ≤3 turns; deterministic fallback; JSONL consensus log. Claude negotiates and explains; code computes all numbers, checks every constraint and decides termination.

## Stack
TBD — chosen once the problem is picked. Candidates: Next.js + Vercel (TypeScript, `@anthropic-ai/sdk`, Stagehand/Playwright) or a Python backend (FastAPI, `anthropic`, Playwright/browser-use). Whichever we pick: a Claude tool-use loop with streaming, every step shown in the UI. Add run/build/deploy commands here once the app exists.

## Roles — one owner per folder, don't edit another person's folder
TBD — fill in names, lanes and folders once decided. Suggested lanes: agent loop and model routing; UI (live agent trace, approval step, output view); tools and data (browser automation, SG APIs, file/PDF output); evals, demo script and pitch.

## Contracts
Agent message schema, consensus-log line format and constraint rule IDs (C-WAKE-1, C-FUEL-1, …) are defined in `docs/challenge-2-framing.md` §4–5. Change them only there, in their own commit, and tell the team. Every lane builds against these.

## Models
- `claude-haiku-5-5`: bulk classify/extract/summarise (keep prompts under 100K tokens)
- `claude-sonnet-5-5`: main agent loop (default)
- `claude-opus-5-5`: one hard step only (planning, final grading, dense vision)
- Cache the system prompt and tool definitions (prompt caching)

## Rules
- Never commit keys. Real keys go in `.env.local` (gitignored); add new variable names to `.env.example`.
- Irreversible actions (send, submit, pay) must wait for the user's approval click.
- No Singpass, CAPTCHAs or logins in the demo path; seed demo data and cache flaky responses.
- Commit small, `git pull --rebase` before pushing, keep `main` deployable.
- Skip test-first TDD; verify the change actually works before saying it's done.
