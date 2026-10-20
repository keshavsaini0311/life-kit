# Your own workspace

1. Run the README quickstart with Python 3.9+.
2. Choose a private data folder. Use ignored workspace/ or an absolute external path.
3. Edit personal/rules.md with your preferences, available time and constraints.
4. Add useful dated facts to the domain context files. Blank is fine.
5. Record a few real observations and generate a report.
6. Add an assistant or connector only for a recurring need.

| Workspace file | Owns |
|---|---|
| life.json | Schema, currency and implemented privacy policy |
| personal/rules.md | Your preferences and boundaries |
| DOMAIN/context.md | Human-readable dated domain context |
| learning/events.jsonl | Canonical typed observations |
| .local/reports/ | Generated reports, safe to regenerate |

The event log is the core's only financial observation store, not a second money
ledger. Recorded spending is not a bank balance or complete spending unless input
is complete. Amounts support two decimal places in v0.1. Currencies requiring other
precision are not supported yet. Distinct currencies are never summed together.

Ask your assistant: "Review my last week using my rules and logged observations.
Suggest one next action that fits my time. Tell me what is stale or unknown."
An empty log doesn't mean you did nothing. Check-ins don't prove study quality.

## Scheduling

Run a report manually first and open the result. With a virtualenv installation,
a cron example is:

```cron
0 21 * * * /absolute/source/.venv/bin/life-kit --workspace /absolute/private/workspace report
```

Replace both paths. Windows can use Task Scheduler; macOS may use a user LaunchAgent.
The starter installs none of them. Schedules use machine-local time; the machine must
be available. There is no wake, catch-up, notification or retry service yet. Reports
replace the same day/window artifact atomically. Writes use a cross-process lock.
Back up your private workspace separately to a destination you control.

## Troubleshooting

- Workspace not initialized: initialize an empty folder and reuse its path.
- No spending recorded: unknown, not zero.
- Invalid event: retain the original log and inspect the reported line. There is no
  correction/migration CLI yet; don't silently delete history.
- Optional CLI absent: local core still works. Installed is not authenticated.
- Permission error: use a writable folder, without disabling machine security.
- Unsupported schema/policy: retain the original and use a matching release or an
  explicit migration. Don't edit a version number to bypass validation.
