---
name: clarify-before-building
description: Ask clarifying questions before acting when a plan, task or requirement is ambiguous, unless the user explicitly says "figure it out yourself". Use when starting or executing any plan or build task.
---

# Clarify before building

Before acting on a plan or task, check whether anything in it is unclear enough that a wrong guess
would waste work. If so, ask first — unless the user has explicitly overridden this.

## Step 1 — Look before asking
Never ask for something you can find yourself. First check:
- The plan, CLAUDE.md, README and any project skills
- The existing code, types and folder structure
- Earlier messages in this conversation

Only what is still unclear after this counts as ambiguous.

## Step 2 — Decide whether it is worth asking

ASK when a wrong guess would change the result or cost real rework:
- Two or more reasonable interpretations that lead to different code, data or output
- Requirements that conflict with each other or with the existing code
- Missing information that decides the design (data shape, which model, which stack, scope)
- Anything hard to undo: deleting files, changing shared interfaces/types, adding dependencies,
  external services, deploying, spending API credits at scale

DO NOT ASK when:
- There is an obvious conventional default (naming, formatting, minor styling)
- The choice is trivial and quick to change later
- The answer is already in the project files or conversation
- The user has given the override (see below)

## Step 3 — How to ask
- Ask BEFORE starting the work, not halfway through.
- Batch all questions into one message. Maximum 4 questions; if there are more, ask only the
  ones that block the work and note the rest as assumptions.
- Make each question quick to answer: give 2–4 concrete options, mark the one you recommend
  with "(recommended)", and say in one line why it matters.
- If part of the task is clear and independent, say so and offer to start on that part while
  waiting.

Format:
```
Before I start, a few things are unclear:

1. <Question> — matters because <one line>.
   a) <option> (recommended)
   b) <option>
2. ...

Reply with e.g. "1a, 2b", or say "figure it out yourself" and I'll use my recommendations.
```

## The override
If the user says "figure it out yourself" (or clearly the same thing, e.g. "figure it out",
"your call", "just decide"):
- Do not ask. Make the most reasonable choice for each open point, preferring the simpler,
  more reversible option.
- Proceed with the work.
- At the top of the response, list the decisions made:
  ```
  Assumptions I made:
  - <decision> — because <reason>
  ```
  so the user can correct any of them quickly.
- The override applies to the current task only. For the next new task, go back to asking
  when something is ambiguous.

Even under the override, still stop and confirm before anything irreversible or destructive
(deleting work, force-pushing, overwriting shared files, large spend).
