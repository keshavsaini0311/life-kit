---
name: daily
description: Run a realistic daily review across the user's enabled Life Kit areas. Use for daily runs, capture and status; status-only requests skip teaching and capture.
---

Read `personal/rules.md` and `LIFE.md` first. For a status/report request, generate
`life-kit --workspace $workspace report`, read the latest maintenance report if present,
and give the short review below. Do not start other workflows from a status request.

For a full daily run, ask how much time is available if unknown. Review the current
records, offer a short `study` session if the learning area is enabled, and capture
only facts the user actually supplies and wants recorded:

- Spending: `life-kit --workspace $workspace spend AMOUNT --category CATEGORY`.
- Explicit sleep, gym or study minutes: `life-kit --workspace $workspace checkin --sleep H --gym yes --study MIN`.
- Study sessions: dated evidence and next topic in `learning/plan.md`.
- Work updates: a dated block in `work/standup.md`.
- Personal notes: a dated block in `personal/now.md`.

Use only enabled areas. Don't invent money values or treat self-reports as observed
results. Don't hand-edit generated ledgers. A planned activity is not completed work.

Generate the report and summarize: what the records show, one or two useful next actions
that fit available time, and anything stale or unknown. Missing days aren't debt.
Reports stay local. This routine never sends messages, purchases or changes accounts.
