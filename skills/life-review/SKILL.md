---
name: life-review
description: Review an initialized Life Kit workspace and suggest realistic next actions from the user's context and logged observations. Use for a daily or weekly review, not account setup or external actions.
---

Ask for the workspace path if it wasn't supplied. Read its AGENTS.md, personal/rules.md
and life.json, then only relevant domain context. Run installed
`life-kit --workspace PATH status` or `python -m lifekit --workspace PATH status` from
the source checkout. If unavailable, review only supplied files and say so.

Check dates before treating context as current. Use explicit observations for numbers.
No records means unknown. Check-in prep minutes are self-reported, not completed
lessons or skill scores. An outcome credits its specific action. Receipts/auto replies/
accepts remain separate from human replies, referrals, interviews and offers.

Give a short review: known facts, what needs refreshing, and one or two next actions
that fit available time. Ask a material missing question when necessary. Don't log
inferred emotions or invented facts. Record user-supplied updates only when requested,
with dates and provenance, using the CLI or owning domain context. Never rewrite
history to improve metrics.

A review doesn't authorize external messages, applications, purchases or account
changes. Reports stay local under the starter policy. Don't send private reports to
notifications. Configuration isn't authentication: identify a verified read before
using connector data. See ../../docs/integrations.md when connection scope matters.
