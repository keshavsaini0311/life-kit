# Life Kit

**A personal workspace you own, with AI-assistant routines that run on your own computer.**

Keep context, money, learning and work in one local folder. Claude Code and Codex share the
same skills there. Scheduled jobs keep your ledger, learning loop and reports fresh, and an
optional Telegram bot lets you run things from your phone. Share the software; keep your data.

## Set up in one command

Requires Python 3.9+. No packages to install. From this folder:

```sh
python3 -m lifekit --workspace ~/life setup
```

Setup asks plain questions, one at a time. Each one tells you **why it is asked, an example
answer, and what happens if you skip it**. Press Enter to accept a suggestion or skip. Answers
save as you go, so stop any time and run the same command to continue. Every question is in
the [setup guide](docs/setup-guide.md) if you want to read them first.

| Setup section | What you get |
|---|---|
| Basics, life areas, rules | `personal/rules.md`, `LIFE.md` routing map, `AGENTS.md` / `CLAUDE.md`, context per area |
| AI assistants | Skills written once in `.agents/skills/`, linked for Claude Code (`.claude/skills`) |
| Plugins | Optional Claude Code plugins (superpowers, context7, …) installed if you say yes |
| Connections | `.mcp.json` (Claude) and `.codex/config.toml` (Codex) with read-only tool lists |
| Scheduled runs | Jobs at times you choose, installed with launchd, systemd/cron or Task Scheduler |
| Phone | Your own Telegram bot, paired to your private chat only |

Then start your assistant inside the workspace, with your connections available:

```sh
python3 -m lifekit --workspace ~/life open claude     # or: open codex
```

Say "daily run", "how am I doing", "I spent 450 on food" or "standup".
The `life` skill routes the request to the right area.

## Skills

`life` (router), `daily`, `learn`, `life-review`, and per area: `finance`, `study` (learning), and `work`.
These help you review records and prepare local notes;
scheduled runs never send messages or change external accounts.

## What runs on its own

Pick any of these during setup. Change a time later with `schedule set`.

| Job | Suggested time | Does |
|---|---|---|
| `maintain` | 21:45 daily | Imports bank CSVs, rebuilds monthly ledgers and the learning report, lists stale data |
| `nightly-report` | your review time | Review of the day and one or two realistic next actions |
| `work-brief` | 08:30 weekdays | Assigned tasks, PRs to review, mentions, service health |
| `inbox-review` | 09:00, 19:00 | Inbox threads, latest sender, deadlines and reply drafts |
| `calendar-prep` | 21:30 | Study and planning windows around your calendar |
| `finance-capture` | Sunday 18:00 | Ledger, unmatched bank rows, broker holdings |
| `receipt-review` | 21:00 | Receipt emails to confirm as spending |
| `learn` | Sunday 19:00 | Learning and routine outcomes from recorded activities |

Jobs are read-only, run once per time slot, never overlap, stop after 15 minutes, and save
reports in `.local/reports/`. Your computer must be on and logged in.

**Ledger and learning maintain themselves.** Drop bank CSVs in `finance/inbox/`. Rows matching
your rules in `finance/rules.json` (e.g. `{"match": "swiggy", "category": "food"}`) post as
observed spending. Transfers, investments, income and unmatched rows are never guessed: they
wait in `finance/imports/review.md` until you add a rule. Monthly ledgers and learning reports
are regenerated from the event log.

## Connections

Optional, and read-only for every scheduled job: Gmail, Google Calendar and Drive, Slack,
GitHub, ClickUp, Notion, Linear, SigNoz, Zerodha Kite, Zepto, Swiggy, Zomato, or your own MCP server. See `life-kit connect list` and the
[integration guide](docs/integrations.md). Configured is not connected: `connect verify ID`
makes one real read and records the result, and `doctor` shows it.

## Everyday commands

```sh
life-kit --workspace ~/life doctor                     # files, connections, schedules
life-kit --workspace ~/life checkin --sleep 7 --gym yes --study 30
life-kit --workspace ~/life spend 120 --category food
life-kit --workspace ~/life action --domain learning --channel practice --target sql-joins --variant worked-example
life-kit --workspace ~/life outcome EVENT_ID completed --evidence "self-report: exercise completed"
life-kit --workspace ~/life run nightly-report         # any job, now
life-kit --workspace ~/life schedule set work-brief 09:00 --days weekdays
life-kit --workspace ~/life schedule install            # or: remove, status
life-kit --workspace ~/life telegram setup              # pair your phone later
```

`life-kit` is `python3 -m lifekit` from this folder, or install it:
`python3 -m venv .venv && . .venv/bin/activate && pip install .` (Windows: `python`, and
`.venv\Scripts\Activate.ps1`).

## Privacy and safety

- Your workspace is local and git-ignored. Secrets live in `.local/secrets.json` (owner-only)
  and config files reference them as environment variables.
- Nothing sends messages, buys or edits tickets on its own. Setup does not authorize it.
- Missing data is **unknown, not zero**. Self-reported values stay labelled as self-reported.
- An AI provider has its own data handling: local files are read by a remote model when you
  let your assistant read them. Telegram replies carry content only for areas you allow.

[Setup guide](docs/setup-guide.md) · [Getting started](docs/getting-started.md) ·
[Architecture](docs/architecture.md) · [Integrations](docs/integrations.md) ·
[GitHub sharing](docs/publishing.md) · [Roadmap](docs/roadmap.md) · [Contributing](CONTRIBUTING.md)

Develop: `python3 -m unittest discover -s tests -v` and `python3 scripts/check_public.py`.
MIT licensed. No telemetry.
