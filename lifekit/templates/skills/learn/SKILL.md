---
name: learn
description: Review recorded activities and outcomes to improve learning and routines. Use for a weekly review, evidence checks or comparing practice approaches.
---

Read `personal/rules.md`, relevant learning context and the latest local report.
Generate the deterministic review with `life-kit --workspace $workspace learn`.
It credits outcomes only to their explicit activity IDs and deduplicates each stage
per activity. Completion, review and demonstrated improvement are different outcomes.

Compare practice approaches or routines only when enough eligible observations exist.
The report requires at least five activities at least seven days old to show rates;
that floor does not prove causality. Recent activities and missing outcomes remain
unknown. Self-reported minutes are not learning quality or assessment evidence.

For each proposed change, name the rule, dated evidence, limits and a practical next
experiment. Change one variable at a time. Don't rewrite rules or historical logs
without the user's request. An activity that needs review is not a failed activity.

Only log things that actually happened. Use `action --domain learning --channel practice
--target TOPIC --variant APPROACH` for a completed activity, then `outcome ID completed
--evidence REFERENCE` for an explicitly reported result. Never guess an ID. Keep the
report local and do not initiate external account actions.
