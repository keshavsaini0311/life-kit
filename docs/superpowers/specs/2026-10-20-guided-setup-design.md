# Guided setup: a Life-equivalent system for anyone

Status: draft for approval · 2026-10-20

## Intent

Life Kit is the public, generic version of a private "Life" workspace that one person
built over months: context files, ten assistant skills, ~10 MCP connections, scheduled
runners and a Telegram phone channel. Today the kit ships only the local core (event
log, check-ins, spend, outcomes, report) and one skill. Anyone else wanting the full
system would have to reverse-engineer it.

Goal: a stranger clones the GitHub repo (or a teammate does), runs **one command**,
answers plain-language questions — each explaining *why it is asked, an example answer,
and whether it can be skipped* — and ends with the same shape of system: personal
context, skills wired into **both Claude Code and Codex**, chosen connections with
verified reads, installed scheduled runners at times they chose, and optionally a
paired Telegram bot.

## Audience

- Public GitHub users on macOS, Linux or Windows, with Claude Code, Codex, or both.
- Teammates of the original author, using the same public repo. Nothing
  employer-specific (internal URLs, service names) is bundled; they add those through
  the generic "custom MCP server" step.

## Goals

1. `life-kit setup` — interactive, resumable question flow that writes a complete workspace.
2. Every question carries: the question, why it matters, an example answer, and
   skip behaviour. Skipped answers are recorded as **unknown**, never a made-up default.
3. Generated context: `personal/rules.md`, domain context files, a `LIFE.md` routing map,
   workspace `AGENTS.md` (also read by Claude via `CLAUDE.md` pointing at it), and a
   `memory/` folder with a `MEMORY.md` index.
4. Skills: generic templates of Life's skills (daily, life, finance, prep, work,
   job-hunt, hiring-outreach, apply-autofill, find-contact, learn, plus existing
   life-review), filled from answers, stored once in `.agents/skills/` with
   `.claude/skills` pointing at the same files (copy on Windows if links are unavailable).
   Only skills for domains the user enabled are installed.
5. Connections: a catalog of optional packs. For each chosen entry setup writes config
   for both assistants (Claude: project `.mcp.json` or printed `claude mcp add`; Codex:
   workspace `.codex/config.toml` or printed `codex mcp add`), shows login steps, then
   offers a **verify** step that performs one real read and records the result.
6. Plugins: a recommended Claude Code plugin list (superpowers, context7, github,
   code-review, skill-creator, frontend-design, …) with install commands; the user picks.
7. Runners: setup asks yes/no per runner and installs it with the OS scheduler at a
   user-chosen time. Times live in `life.json` and can be changed later
   (`life-kit schedule set <runner> HH:MM [days]` then re-install).
8. Telegram bot: optional, owner-paired phone channel with configurable notification
   times, same commands as Life's minus anything the user did not enable.
9. `docs/setup-guide.md`: every question, explained, readable before running anything.

## Non-goals

- Copying any data, config, tokens, browser sessions or memory from the private Life
  workspace. Templates are written fresh from Life's *structure*.
- Hosted/multi-user service, web UI, mobile app other than Telegram, WhatsApp.
- Automated claude.ai account connectors (Gmail, Calendar, Slack, Drive). These cannot
  be scripted; setup explains the clicks and verifies afterwards.
- Installing the author's personal hooks (GSD, caveman) — they are personal taste.

## Anti-goals (failure even if it works)

- Setup claims "connected" when only configured. Status must keep **configured /
  authenticated / last verified read** separate; expired = unknown, not zero.
- Setup or any runner sends a message, submits an application, edits a ticket or buys
  anything by default. Outreach/apply skills ship **drafts-only**; sending is a separate,
  explicit opt-in recorded in `life.json` with date.
- Secrets printed to the terminal, written to logs, or placed inside the repo. Secrets
  are prompted with hidden input and stored only in the workspace (mode 0600) or the
  assistant's own config.
- Private report content sent to Telegram. Notifications say "report ready / failed"
  unless the user explicitly changes that rule.
- The core gaining a non-stdlib dependency.

## Constraints (from AGENTS.md and the existing code)

- Python 3.9+, standard library only. Network access only inside optional connection
  verify/bot code, never in core commands.
- All state under `--workspace`; never assume username, timezone, currency, employer.
- Preserve existing invariants: exact decimal money, explicit outcome IDs,
  unknown-vs-zero, self-reported-vs-observed, atomic `private_write`, `locked()`.
- Tests use temporary workspaces and a fake HOME; no live accounts in CI. The public
  check (`scripts/check_public.py`) must keep passing; templates go under `lifekit/`
  as package data so they ship with `pip install`.

## Decided by the user

- Audience: public GitHub **and** teammates.
- Assistants: **both Claude Code and Codex**, same skill files.
- Runners: setup **installs** them (after per-runner yes/no) with **configurable times**.
- Telegram bot: **included**, times configurable.
- Sending: **drafts only in v1.** No automated send path. Skills prepare drafts; a
  send happens only when the user asks the assistant in a live chat. The `sending`
  opt-in key is recorded in `life.json` for later versions but enables nothing in v1.
- Bot replies: **like Life.** Per-domain `telegram.reply_domains` in `life.json`;
  default `career` (prep/job replies) on, `personal`, `finance`, `work` off, which get
  only "ready / failed / done". `/report` sends status only unless every domain the
  report covers is enabled for replies. `/ask` replies in chat only when its task was
  scoped to reply-enabled domains; otherwise "done, saved locally".

## Design

### Question flow (`life-kit setup`)

Sections in order; each can be skipped as a whole. Answers save after every question
to `workspace/.local/setup-answers.json`, so Ctrl-C and re-run resumes.
`--answers FILE` runs non-interactively (tests, re-provisioning).

1. **Basics** — name to address you by, timezone (default: detected, confirm),
   currency, where the workspace lives.
2. **Domains** — which to enable: personal, finance, career (prep / job search /
   resume), work, learning. Drives which questions, skills and runners appear.
3. **Rules & routine** — working hours, when you have free time, best time for a daily
   review, privacy rules (what may leave the machine), tone you want from the assistant.
4. **Domain context** — per enabled domain, a few questions (finance: monthly in-hand
   income, baseline spend, savings goal; career: current role, target role/comp,
   timeline, resume path; work: employer, role, tools used; personal: health/routine
   goals). Numbers are stored with the date they were given.
5. **Assistants** — detect `claude`/`codex` on PATH; choose which to wire.
6. **Plugins** (Claude only) — recommended list, multi-select.
7. **Connections** — catalog filtered by enabled domains; multi-select, then per entry:
   config written, login instructions shown, "verify now?" (needs the assistant CLI).
8. **Runners** — per runner: enable? time? days?
9. **Telegram** — enable? then BotFather instructions, hidden token prompt, pairing.
10. **Summary** — what was written, what is configured vs verified, next commands.

Question definitions live in one data structure (id, section, prompt, why, example,
skip behaviour, validator, depends-on). The CLI and `docs/setup-guide.md` both derive
from it; a test fails if the guide is missing a question.

### Connection catalog

Each entry: id, purpose, domains, which assistants support it, config snippet per
assistant, login steps, secret fields (if any), **allowed read tools** for runners,
excluded write tools, verify tool + arguments, provider docs URL, `official | community`
label. Initial entries (re-check tool names against provider docs when building):

| Pack | Entries |
|---|---|
| Mail/calendar/files | Gmail, Google Calendar, Google Drive (claude.ai connectors; Codex apps where available) |
| Work | GitHub (`gh` CLI + MCP), ClickUp, Slack, Notion, Linear, SigNoz (self-hosted, URL + key), **custom MCP** (URL or command) |
| Career | LinkedIn (community server, flagged as such) |
| Finance | Zerodha Kite (official, read-only tools only) |
| Shopping (India) | Zepto, Swiggy Instamart, Swiggy Food, Zomato — order/history reads; checkout tools excluded |

Verify: `life-kit connect verify <id>` runs the chosen assistant non-interactively with
**only that server and only its verify tool** allowed, then writes
`.local/connections.json` (`configured`, `authenticated`, `last_read_at`, `status`:
ok/unavailable/expired/partial, sanitized error category). `life-kit doctor` shows it.

### Runners

Generic ports of Life's routines. Each is a runner id, default time (shown as a
suggestion, user confirms or changes), the assistant task prompt, and its read-tool
allowlist:

| Runner | Suggested time | Needs |
|---|---|---|
| nightly-report | 22:00 daily | core only (+ any verified connection results) |
| work-brief | 08:30 weekdays | work connections |
| inbox-review | 09:00, 19:00 | Gmail |
| calendar-prep | 21:30 | Calendar |
| finance-capture | Sun 18:00 | Kite and/or bank CSV inbox |
| receipt-review | 21:00 | Gmail |
| job-discovery | 08:00 | career; public listings only, drafts only |

Execution: `life-kit run <runner>` — single-instance lock, skip-if-already-succeeded
today, timeout (default 15 min) with process-group kill, snapshot saved before the
agent starts so a failure still leaves a report, status in `.local/runners/status.json`,
output to `.local/reports/`. Agent invocation:
- Codex: `codex exec --ephemeral` with apps/plugins/browser/computer-use disabled and
  only the runner's MCP servers enabled with `enabled_tools` = its allowlist.
- Claude: `claude -p` with `--allowedTools` = the runner's read tools and no write tools.
Agent choice per runner defaults to the one the user picked as primary.

Scheduling: `life-kit schedule install|remove|status|set`:
- macOS: user LaunchAgent (`~/Library/LaunchAgents`, `StartCalendarInterval`).
- Linux: systemd user timer if `systemctl --user` works, else a marked crontab block.
- Windows: `schtasks` per runner.
`--dry-run` prints the files/commands without touching the system (used by tests).
Setup asks before installing anything. macOS Desktop/Full-Disk-Access caveat
(LaunchAgent cannot read `~/Desktop`) is surfaced in setup when the workspace is there.

### Automatic ledger, learning and maintenance (added 2026-10-20)

The user asked that the ledger and learning update themselves and the workspace keeps
itself maintained, without a manual run.

- **Ledger.** Bank CSVs dropped into `finance/inbox/` are parsed (date, description,
  debit, credit, balance, reference; header detection), deduplicated across overlapping
  exports while keeping distinct identical purchases, and matched against
  `finance/rules.json` (`{"match": text, "category": c}` or `{"match": text, "kind":
  "transfer"|"investment"|"income"}`). Matching debits are posted automatically as
  `spend` events marked `source: bank-csv` with their reference (observed, not
  self-reported). Transfers/investments/credits are never spend. Unmatched rows stay in
  `finance/imports/review.md`; the finance skill helps the user add rules, after which the
  next run posts them. `finance/ledger/YYYY-MM.md` is regenerated from events (owned by
  the generator; humans edit events/rules, not the file), totals per currency, with
  "unknown, not zero" when a month has no input and a pending-review count.
- **Learning.** A deterministic report from the event log: actions and stage counts per
  channel and variant (one count per action per stage), rates shown only when n ≥ 5 and
  only for actions older than 7 days, open actions older than 14 days without an outcome
  listed as follow-up candidates. Written to `learning/reports/YYYY-MM-DD.md`. The
  `learn` skill (agent runner, weekly) reads it and proposes rule changes; it never edits
  rules on its own.
- **Maintenance.** `life-kit maintain`, nightly before the report: import + post +
  regenerate this and last month's ledger, refresh the learning report, and write a
  freshness list (context files untouched > 30 days, connections never verified or last
  read > 7 days, no check-in for 3 days, a month with no money input) to
  `.local/reports/maintenance-YYYY-MM-DD.md`, which the nightly report reads.
- New runners: `maintain` 21:45 daily (local, no agent), `learn` 19:00 Sunday (agent).
  Telegram gains `/spend AMOUNT CATEGORY [note]`.

### Telegram bot

Stdlib port of Life's `automation/mobile/`: HTTPS long polling (no public port),
hidden token prompt, bot identity check, refuse if a webhook is set, 5-minute one-time
pairing command establishes the single owner, owner cannot change from chat. Commands:
`/help /status /report /checkin /outcome /cancel` plus one per enabled runner, and
`/ask` (read-only local agent task). Queue in workspace SQLite (stdlib `sqlite3`),
commands older than 30 min expire, one poller at a time. Installed as a service by the
same scheduler module (LaunchAgent KeepAlive / systemd user service / Windows task at
logon). Notification times configurable; content is status-only by default. Career
autonomy (Life's `/auto`) is **not** ported in v1 — drafts only.

## Settled after builder review (author's calls)

- **Source material:** the builder of this kit (the author's assistant session) may
  read the private Life workspace's skills, runner and bot *code* for structure and
  hard-won rules, and writes generic templates fresh. No names, numbers, paths,
  contacts, config values or memory are copied. `check_public.py` gains a check that
  templates contain no home paths or personal identifiers.
- **Schema:** `life.json` moves to `schema_version: 2` with new optional keys
  (`profile`, `domains`, `assistants`, `runners` with times, `telegram`, dated
  `sending` opt-ins). `core.load` accepts 1 and 2; `life-kit migrate` upgrades 1 → 2
  in place (atomic, backup kept). Setup works on a new folder **or** an existing
  workspace: it adds missing files and never overwrites an existing file — it writes
  `FILE.suggested` beside it instead.
- **Connector reach per assistant:** each catalog entry declares which assistants can
  reach it headless. Runners default to the assistant that can; if only Claude can
  (claude.ai connectors), the runner uses Claude. Codex runners may enable *apps* only
  when the runner's entry requires it, still restricted to its read allowlist.
  Whether `claude -p` sees claude.ai connectors headless is verified at build time;
  if not, those entries are marked interactive-only and their runners hidden.
- **Two-a-day runners** keep one "already succeeded" marker per scheduled slot.

## Left to the builder

- File/module layout inside `lifekit/` (e.g. `setup.py`-style module names, templates
  dir), as long as templates ship as package data and the core stays stdlib.
- Exact wording of questions and the guide, within the why/example/skip rule.
- Whether generic skill templates use simple `string.Template` placeholders or similar.
- How much of Life's dashboard (domain-markdown parsing) to port vs extending the
  existing event-log report. Prefer extending the existing report.
- Order of implementation; suggested: question flow + context → skills → connections
  catalog + verify → runners + scheduler → Telegram → guide.

## Open risks

- Assistant CLI flags (`claude -p --allowedTools`, `codex exec -c …`) change between
  versions; verify against current docs at build time and fail clearly when unsupported.
- Provider MCP endpoints and tool names drift; the catalog records a docs URL per entry.
- Windows symlinks and schedulers are the least tested path; CI covers dry-run only.
