# Getting started

1. Install Python 3.9 or newer. Nothing else is required for the core.
2. Optional: install Claude Code (`claude`) and/or Codex (`codex`) and sign in. Setup detects them.
3. Run `python3 -m lifekit --workspace ~/life setup` from this folder and answer the questions.
   Read [the setup guide](setup-guide.md) first if you like; it explains every question.
4. Log in to the connections you picked (setup prints the steps), then check each one:
   `python3 -m lifekit --workspace ~/life connect verify gmail`.
5. Try a job by hand before scheduling it: `python3 -m lifekit --workspace ~/life run nightly-report`.
   Open the report it prints. When happy: `... schedule install`.
6. Work with your assistant inside the workspace: `python3 -m lifekit --workspace ~/life open claude`.

Choose a workspace folder outside this repository (for example `~/life`). On macOS, avoid
`~/Desktop`, `~/Documents` and `~/Downloads`: background jobs need extra privacy permission
to read those folders. Re-running setup asks only new questions and never overwrites a file
you edited. It writes `FILE.suggested` beside it instead.

| Workspace file | Owns |
|---|---|
| `life.json` | Schema, currency, areas, assistants, connections, job times, Telegram choices |
| `personal/rules.md` | Your preferences and boundaries; every assistant reads it first |
| `LIFE.md`, `AGENTS.md`, `CLAUDE.md` | Routing map and assistant instructions |
| `<area>/context.md` | Dated context per area |
| `.agents/skills/` | Shared skills (`.claude/skills` points here) |
| `learning/events.jsonl` | Canonical typed observations (check-ins, spending, actions, outcomes) |
| `finance/inbox/`, `finance/rules.json` | Bank CSVs in, category rules |
| `finance/ledger/YYYY-MM.md`, `learning/reports/` | Generated; don't hand-edit |
| `.local/` | Reports, logs, secrets, connection and job status (private) |

## Scheduling notes

Jobs use your computer's local time and only run while it is on and logged in. launchd and
systemd catch up a missed run after wake; cron and Task Scheduler may not. Each job runs once
per time slot; a failed run can be retried with `life-kit run ID`. Jobs read; they never send.

## Troubleshooting

- `doctor` shows files, connections (configured vs verified) and whether jobs are installed.
- A job log says `Operation not permitted` (macOS): allow Python under System Settings →
  Privacy & Security → Files and Folders / Full Disk Access, or move the workspace to `~/life`.
- A job says `claude not installed`: reinstall schedules after installing the CLI, because jobs
  keep the PATH from install time (`schedule install`).
- No spending recorded: unknown, not zero. Unmatched bank rows wait in `finance/imports/review.md`.
- Invalid event: the original log is kept and the line is reported; don't delete history.
- Unsupported schema: run `life-kit migrate` (keeps `life.json.v1.bak`).
- Telegram silent: `life-kit telegram check`; the service must be installed (`schedule install`).
