# Guided Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `life-kit setup` turns an empty folder into a Life-equivalent workspace — context, skills for Claude + Codex, verified connections, a self-maintaining ledger and learning loop, scheduled runners, Telegram bot — through explained questions.

**Architecture:** Small stdlib modules beside the existing `core.py`/`cli.py`. One question table drives the wizard and the guide. Static catalogs (connections, plugins, runners) are plain Python data. Generated files come from `string.Template` files shipped as package data. Anything that touches the OS or network takes an injectable function so tests stay offline.

**Tech Stack:** Python 3.9+ stdlib (`argparse`, `json`, `string.Template`, `sqlite3`, `urllib`, `subprocess`), `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-20-guided-setup-design.md`

## Global Constraints

- Python 3.9+, standard library only; `dependencies = []` stays empty.
- All state under `--workspace`; never assume username, timezone, currency, employer, account.
- Skipped answer → stored as `null` and rendered as "unknown"; never a default value.
- Never overwrite an existing workspace file: write `NAME.suggested` beside it.
- Secrets: hidden input (`getpass`), stored only in `workspace/.local/secrets.json` mode 0600 or the assistant's own config; never printed or logged.
- No send/submit/purchase path. Outreach/apply skills are drafts-only. `sending` key enables nothing in v1.
- Telegram replies: domains in `telegram.reply_domains` (default `["career"]`) may carry content; others get status only.
- Tests: temp workspaces, fake HOME, injected runners; no network, no real scheduler.
- `python3 -m unittest discover -s tests -v` and `python3 scripts/check_public.py` pass after every task.
- No content copied from the private Life workspace: no names, numbers, paths, contacts, config values.

## Review Focus

1. Re-running setup on a half-finished or existing workspace → resumes, never clobbers edited files (Task 3 test `test_rerun_keeps_edits`).
2. Secret typed at the token/key prompt → never appears in stdout, logs, `setup-answers.json` (Task 3 `test_secret_not_in_answers`, Task 8 `test_token_not_logged`).
3. Runner fires twice in the same slot or while one is running → second is skipped, not duplicated (Task 6 `test_same_slot_skips`, `test_lock_held_skips`).
4. Agent CLI absent or times out → status `unavailable`/`timeout`, snapshot still written (Task 6 `test_missing_agent`, `test_timeout_keeps_snapshot`).
5. Telegram message from a non-owner or stale command → ignored / expired, never executed (Task 8 `test_non_owner_ignored`, `test_stale_command_expires`).

---

### Task 1: Schema v2 + migrate

**Files:** Modify `lifekit/core.py`, `lifekit/cli.py`; Test `tests/test_core.py`

**Interfaces — Produces:**
- `core.SCHEMA = 2`; `core.load(root) -> (Path, dict)` accepts 1 or 2.
- `core.migrate(root) -> Path` (backup path `life.json.v1.bak`); no-op error if already 2.
- `core.update_config(root, fn) -> dict` — under `locked()`, load, `fn(cfg)` mutates, atomic write.
- v2 keys (all optional): `profile`, `domains` (list), `assistants` (list of `"claude"|"codex"`), `primary_assistant`, `runners` (`{id: {"enabled": bool, "times": ["HH:MM"], "days": "daily"|"weekdays"|"sun".."sat"}}`), `telegram` (`{"enabled", "reply_domains", "notify_times"}`), `sending` (`{}`).
- CLI: `life-kit migrate`.

- [ ] Tests: `test_init_writes_v2`, `test_load_accepts_v1`, `test_migrate_v1_to_v2_keeps_backup` (backup content == original), `test_update_config_atomic` (fn raising leaves file unchanged), `test_load_rejects_v3`.
- [ ] Run, see fail; implement; run all tests pass; commit `feat: life.json schema v2 and migrate`.

### Task 2: Question table, wizard, guide

**Files:** Create `lifekit/questions.py`, `lifekit/wizard.py`, `docs/setup-guide.md`; Modify `lifekit/cli.py`; Test `tests/test_wizard.py`

**Interfaces — Produces:**
- `questions.QUESTIONS: list[dict]` keys: `id, section, prompt, why, example, skip` (text of what skipping means), `kind` (`text|choice|multi|time|number|secret|yesno`), `choices` (optional), `when` (optional `callable(answers)->bool`), `default` (optional callable(answers) — only for detected values like timezone; user confirms).
- `questions.SECTIONS`: ordered `(id, title, intro)` for the 10 spec sections.
- `wizard.run(root, io=ConsoleIO(), answers_path=None) -> dict` — loads `.local/setup-answers.json`, asks only unanswered questions whose `when` holds, saves after each answer, then calls `render.apply(root, answers)` (Task 3). Typing `skip` stores `None`; `back` re-asks previous.
- `wizard.ConsoleIO` with `ask(text, secret=False) -> str` and `say(text)`; tests pass a scripted fake.
- `questions.guide_markdown() -> str`; CLI `life-kit guide` prints it; `docs/setup-guide.md` is its output.
- CLI: `life-kit setup [--answers FILE]` (FILE = JSON dict used instead of prompts; validated identically). Setup on a nonexistent/empty folder calls `core.init` first; on a v1 workspace calls `migrate`.

Each prompt printed as: question, then `Why: …`, `Example: …`, `Skip: …`. Validation errors re-ask with the reason. Secrets via `getpass`, stored to `.local/secrets.json` (0600) and recorded in answers only as `"<stored>"`.

- [ ] Tests: `test_every_question_has_why_example_skip`, `test_skip_records_none`, `test_resume_skips_answered` (pre-seeded answers file → those prompts not shown), `test_when_hides_finance_questions_if_domain_off`, `test_invalid_time_reasks`, `test_answers_file_noninteractive`, `test_guide_matches_docs` (`guide_markdown() == Path('docs/setup-guide.md').read_text()`), `test_secret_not_in_answers`.
- [ ] Implement; tests pass; regenerate guide; commit `feat: explained setup questions and resumable wizard`.

### Task 3: Render workspace context + skills

**Files:** Create `lifekit/render.py`, `lifekit/templates/workspace/{rules.md,LIFE.md,AGENTS.md,CLAUDE.md,MEMORY.md,<domain>.md}`, `lifekit/templates/skills/<name>/SKILL.md` for: life, daily, finance, prep, work, job-hunt, hiring-outreach, apply-autofill, find-contact, learn, life-review (moved from `skills/`); Modify `pyproject.toml` (package-data `templates/**/*`), `scripts/check_public.py`, `README.md`; Test `tests/test_render.py`

**Interfaces:**
- Consumes: answers dict from Task 2.
- Produces: `render.apply(root, answers) -> list[str]` (relative paths written or `*.suggested`). `render.write_new(path, text) -> Path` implements never-overwrite (identical content → no-op). `render.SKILLS_BY_DOMAIN: dict[str, list[str]]` (`life`, `daily`, `learn`, `life-review` always; finance→finance; career→prep, job-hunt, hiring-outreach, apply-autofill, find-contact; work→work).
- Skills written to `.agents/skills/<name>/SKILL.md`; `.claude/skills` symlink to `../.agents/skills`, falling back to a copy when `os.symlink` raises.
- Placeholders: `$name $timezone $currency $workspace $review_time $domains` plus per-domain answers; missing → `unknown`.

Skill templates: rewrite from Life's skill *structure* (triggers, steps, filing rules, unknown-vs-zero, untrusted connector content) with no personal facts. hiring-outreach/apply-autofill/find-contact state **drafts only: never send or submit; the user sends**. Scripts are not ported.

`check_public.py`: add `lifekit/templates` coverage (already under `lifekit`) and a pattern flagging email addresses whose domain isn't `example.com|example.org|anthropic.com|users.noreply.github.com`.

- [ ] Tests: `test_apply_writes_core_files`, `test_skipped_answer_renders_unknown`, `test_rerun_keeps_edits` (edit rules.md, rerun → original kept, `rules.md.suggested` written), `test_skills_follow_domains`, `test_claude_skills_points_to_agents`, `test_outreach_skills_say_drafts_only`, `test_templates_have_no_unfilled_placeholders` (render with full answers, assert no `$` identifiers left).
- [ ] Implement; tests + public check pass; commit `feat: render workspace context and shared skills`.

### Task 4: Connection + plugin catalog, config writers, verify

**Files:** Create `lifekit/catalog.py`, `lifekit/connections.py`; Modify `lifekit/cli.py`, `docs/integrations.md`; Test `tests/test_connections.py`

**Interfaces — Produces:**
- `catalog.CONNECTIONS: list[dict]` keys: `id, title, domains, source` (`official|community|account`), `docs`, `claude` (`{"type":"http","url":…}` | `{"command":…, "args":[…]}` | `{"account": "Gmail"}` for claude.ai connectors), `codex` (same shape or `None`), `secrets` (list of `{"name","env","prompt"}`), `login` (list of steps, text), `read_tools` (list), `verify` (`{"tool":…, "args":{…}}`), `headless` (list of assistants able to read it unattended).
  Entries: gmail, google-calendar, google-drive, github, clickup, slack, notion, linear, signoz, custom, linkedin, kite, zepto, swiggy-instamart, swiggy-food, zomato. Verify URLs/tool names against provider docs while writing; record each `docs`.
- `catalog.PLUGINS: list[dict]` `{id, why, install}` (e.g. `claude plugin install superpowers@claude-plugins-official`).
- `connections.write_configs(root, ids, custom=None) -> list[str]` — writes `.mcp.json` (Claude project scope; `${ENV}` references for secrets, never literal values) and `.codex/config.toml` (`[mcp_servers.<id>]` + `enabled_tools = read_tools`; secrets via `env_vars`/`bearer_token_env_var`), never overwriting (merge only new ids; existing ids untouched). Also writes `.local/env.sh` (0600) exporting stored secrets for runners.
- `connections.verify(root, id, assistant, run=subprocess.run) -> dict` — runs Claude `claude -p --strict-mcp-config --mcp-config .mcp.json --allowedTools mcp__<id>__<tool> --output-format json "<fixed prompt>"` or Codex `codex exec --ephemeral -c features.apps=<needed> …`; parses; writes `.local/connections.json[id] = {configured, authenticated, last_read_at, status, error}`; error is a category (`absent|auth|timeout|tool|unknown`), never raw output.
- `connections.status(root) -> dict`.
- CLI: `life-kit connect list|add ID…|verify ID [--assistant claude|codex]|status`, `life-kit plugins` (prints list + commands). Wizard sections 6–7 call these.


- [ ] Tests: `test_every_entry_has_login_verify_docs`, `test_mcp_json_uses_env_refs_not_secrets`, `test_codex_toml_limits_tools`, `test_write_configs_keeps_existing_servers`, `test_verify_ok_records_last_read` (fake run returns success JSON), `test_verify_missing_cli_is_absent_not_ok`, `test_verify_error_is_category_only` (fake stderr containing a token string → not in connections.json).
- [ ] Implement; pass; commit `feat: connection catalog with dual-assistant config and verified reads`.

### Task 5: Automatic ledger, learning report, maintenance

**Files:** Create `lifekit/ledger.py`, `lifekit/learning.py`, `lifekit/maintain.py`; Modify `lifekit/core.py` (spend gains `source="self-report"`, `ref=None`; snapshot/report count observed vs self-reported separately), `lifekit/cli.py`; Test `tests/test_ledger.py`, `tests/test_learning.py`

**Interfaces — Produces:**
- `ledger.parse_csv(path) -> list[{"date": "YYYY-MM-DD", "description", "debit": Decimal|None, "credit": Decimal|None, "balance", "ref"}]` — header row detected by aliases (`date|txn date|value date`, `narration|description|particulars`, `withdrawal|debit|dr`, `deposit|credit|cr`, `ref|reference|chq`); accepts `DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`, `DD Mon YYYY`; amounts with commas; unparseable rows → `errors` list, file kept.
- `ledger.import_inbox(root) -> {"posted": n, "review": n, "skipped_dup": n, "errors": [...]}` — reads `finance/inbox/*.csv`; row key = sha256(date, debit, credit, ref or description, occurrence-index-within-file-for-that-tuple) so overlapping exports dedupe but two identical purchases in one export both count; posts via `core.spend(..., source="bank-csv", ref=key, request_id=key)`; moves processed files to `finance/inbox/processed/`; writes `finance/imports/review.md` (unmatched debits) and leaves credits out of spend.
- `ledger.load_rules(root) -> list[dict]`; first case-insensitive substring match wins; kinds `transfer|investment|income` never post.
- `ledger.render(root, month "YYYY-MM") -> Path` — `finance/ledger/YYYY-MM.md`, header `<!-- generated by life-kit; edit events or finance/rules.json -->`, rows by day, totals per currency and category, `Spending: unknown, not zero` when no spend events, pending review count.
- `learning.report(root, today=None) -> Path` — `learning/reports/YYYY-MM-DD.md`: per channel×variant actions, stages (one per action), rate only if eligible n ≥ 5 (eligible = action ≥ 7 days old) else `too few`, follow-ups = actions > 14 days old without outcome.
- `maintain.run(root, today=None) -> Path` — import_inbox, render current+previous month, learning.report, freshness list (context mtime > 30 d, connection status not ok or `last_read_at` > 7 d, no checkin in 3 d, month without spend input) → `.local/reports/maintenance-YYYY-MM-DD.md`.
- CLI: `life-kit ledger import|render [YYYY-MM]`, `life-kit learn`, `life-kit maintain`.

- [ ] Tests: `test_parse_common_bank_headers`, `test_overlapping_exports_dedupe`, `test_identical_purchases_in_one_export_both_post`, `test_transfer_rule_not_spend`, `test_unmatched_goes_to_review`, `test_rule_added_then_rerun_posts` (no double post of earlier rows), `test_credit_never_spend`, `test_bad_date_row_reported_file_kept`, `test_ledger_unknown_not_zero`, `test_ledger_multi_currency_not_summed`, `test_learning_rate_needs_five_eligible`, `test_recent_actions_excluded_from_rates`, `test_followups_listed_after_14_days`, `test_maintain_writes_freshness`.
- [ ] Implement; pass; commit `feat: automatic ledger, learning report and maintenance`.

### Task 6: Runners

**Files:** Create `lifekit/runners.py`, `lifekit/templates/runners/<id>.md` (task prompts); Modify `lifekit/cli.py`; Test `tests/test_runners.py`

**Interfaces — Produces:**
- `runners.RUNNERS: dict[id, {"title","times","days","needs"(connection ids or []), "domains", "prompt"}]` — ids/times from spec: nightly-report 22:00 daily; work-brief 08:30 weekdays; inbox-review 09:00+19:00 daily; calendar-prep 21:30 daily; finance-capture 18:00 sun; receipt-review 21:00 daily; job-discovery 08:00 daily; maintain 21:45 daily (`kind: local` → runs `maintain.run`, no agent); learn 19:00 sun (agent, uses learn skill + latest learning report). Each entry has `kind: agent|local`.
- `runners.available(cfg, conn_status) -> list[id]` — domain enabled and every needed connection configured.
- `runners.command(root, cfg, runner_id) -> list[str]` — Claude: `claude -p --strict-mcp-config --mcp-config .mcp.json --allowedTools <read tools of needs> --permission-mode default`; Codex: `codex exec --ephemeral --skip-git-repo-check --cd ROOT --sandbox read-only -c features.plugins=false -c features.browser_use=false -c features.computer_use=false -c features.apps=<true only if a need is account-sourced>`; assistant = first in `headless` of needs that the user enabled, else primary.
- `runners.run(root, runner_id, now=None, run=subprocess.Popen, timeout=900, force=False) -> dict` — slot = latest scheduled time ≤ now (same day); skip if `.local/runners/status.json[id][slot]=="ok"` unless force; non-blocking lock `.local/runners/<id>.lock` (held → `skipped-locked`); write `core.report` snapshot first; run agent with prompt on stdin, kill process group on timeout; save output to `.local/reports/<date>-<id>.md`; record status `ok|failed|timeout|unavailable`. Returns the status record.
- CLI: `life-kit run ID [--force]`.

- [ ] Tests: `test_available_filters_by_domain_and_connection`, `test_claude_command_allowlist_only_reads`, `test_codex_command_read_only`, `test_same_slot_skips`, `test_second_slot_runs` (inbox at 19:05 after 09:00 ok), `test_lock_held_skips`, `test_missing_agent` (→ unavailable, snapshot exists), `test_timeout_keeps_snapshot` (fake process sleeping; timeout=1).
- [ ] Implement; pass; commit `feat: bounded single-instance runners`.

### Task 7: OS scheduler

**Files:** Create `lifekit/schedule.py`; Modify `lifekit/cli.py`; Test `tests/test_schedule.py`

**Interfaces — Produces:**
- `schedule.jobs(root, cfg) -> list[{"label","argv","times","days"}]` — one per enabled runner, plus telegram service (`keepalive=True`) when enabled. Label `io.lifekit.<hash8 of root>.<id>` so two workspaces never collide.
- `schedule.plan(jobs, platform=sys.platform, home=Path.home()) -> list[{"path"|"command", "content"}]`:
  - darwin: plist per job in `home/Library/LaunchAgents/`, `StartCalendarInterval` array (one dict per time × weekday), `KeepAlive` for service, stdout/stderr to `ROOT/.local/logs/`.
  - linux: `home/.config/systemd/user/<label>.{service,timer}` with `OnCalendar=` (`Mon..Fri *-*-* 08:30:00`); fallback crontab block between `# BEGIN life-kit <hash8>` / `# END …` when `systemctl --user` unavailable.
  - win32: `schtasks /Create /F /TN <label> /SC DAILY|WEEKLY /D … /ST HH:MM /TR "<argv>"`.
- `schedule.install(root, dry_run=False, run=subprocess.run)`, `remove(...)`, `status(...)`. `dry_run` returns the plan text.
- `life-kit schedule set ID HH:MM[,HH:MM] [--days daily|weekdays|sun..sat]` → `core.update_config`. Validates `HH:MM` 00:00–23:59.
- Wizard section 8 asks per runner (enable, times, days) then offers install (yes/no); macOS + workspace under `~/Desktop|~/Documents|~/Downloads` prints the Full-Disk-Access note.

- [ ] Tests: `test_launchd_plist_times_weekdays` (plistlib parse → 5 entries for weekdays 08:30), `test_systemd_oncalendar`, `test_cron_block_replaced_not_duplicated`, `test_schtasks_args`, `test_labels_differ_per_workspace`, `test_set_rejects_bad_time`, `test_install_dry_run_touches_nothing` (fake home stays empty).
- [ ] Implement; pass; commit `feat: install runners with configurable times on macOS, Linux, Windows`.

### Task 8: Telegram bot

**Files:** Create `lifekit/telegram.py`; Modify `lifekit/cli.py`; Test `tests/test_telegram.py`

**Interfaces — Produces:**
- `telegram.Api(token, opener=urllib.request.urlopen)` with `call(method, **params) -> dict`; token never in exceptions/logs (wrap errors as `TelegramError(category)`).
- `telegram.setup(root, io, api_factory=Api) -> None` — hidden token prompt, `getMe`, refuse when `getWebhookInfo.url` set, store token in `.local/secrets.json`, show one-time `/pair <16 hex>` valid 5 min; `poll_once` that receives it from a private chat stores owner `chat_id` in `life.json` `telegram.owner`.
- `telegram.Queue(root)` — sqlite at `.local/telegram.sqlite3`: `add(kind, text) -> task_id`, `next() -> row|None`, `finish(id, status)`, `cancel(id)`, `recent(5)`.
- `telegram.handle(root, cfg, message, now) -> str|None` — reply text. Non-owner or group → `None`. Message older than 30 min → "expired". Commands: `/help /status /report /checkin k=v… /spend AMOUNT CATEGORY [note] /outcome ID STAGE [evidence] /cancel ID /ask TEXT` + `/<runner-id>` for enabled runners. `/checkin` and `/outcome` call `core.checkin`/`core.outcome` directly.
- `telegram.reply_text(cfg, domains, content, status) -> str` — content only when every domain ⊆ `reply_domains`, else status line.
- `telegram.run(root, api, stop)` — long polling `getUpdates(timeout=50, offset)`, single-instance lock, worker executes queued tasks via `runners.run`/agent `/ask` (read-only command from Task 6 builder with no MCP), sends status/permitted content; `notify_times` sends "nightly report ready/failed".
- CLI: `life-kit telegram setup|check|run`. Scheduler (Task 7) installs `run` as keep-alive service.

- [ ] Tests: `test_non_owner_ignored`, `test_stale_command_expires`, `test_pairing_code_expires_after_5_min`, `test_refuses_existing_webhook`, `test_checkin_command_writes_event`, `test_finance_reply_is_status_only`, `test_career_reply_has_content`, `test_token_not_logged` (Api error with token in URL → message lacks token), `test_cancel_queued`.
- [ ] Implement; pass; commit `feat: owner-paired Telegram channel`.

### Task 9: Wire wizard end-to-end, docs, final checks

**Files:** Modify `lifekit/wizard.py` (sections 5–10 call Tasks 4–7), `README.md`, `docs/getting-started.md`, `docs/architecture.md`, `docs/roadmap.md`, `docs/setup-guide.md`, `AGENTS.md`; Test `tests/test_e2e.py`

- [ ] Test `test_full_setup_from_answers_file`: answers JSON enabling all domains, both assistants, gmail+github, two runners, telegram off → workspace contains rules, LIFE.md, AGENTS.md, CLAUDE.md, skills, `.mcp.json`, `.codex/config.toml`, `life.json` runner times; `schedule.install(dry_run=True)` lists both runners; nothing outside temp dirs touched.
- [ ] Summary screen lists configured vs verified per connection and exact next commands.
- [ ] README quickstart becomes `python3 -m lifekit --workspace ~/life setup`; roadmap items 1–3 and 8 marked done; architecture diagram adds wizard/runners/bot.
- [ ] Full test suite + public check + `python3 -m lifekit --workspace $(mktemp -d)/w setup --answers examples/answers.json` (new fictional file) run clean; commit `feat: one-command guided setup`.
