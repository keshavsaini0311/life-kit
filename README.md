# Life Kit

**A personal workspace you own, with routines an AI assistant can help you run.**

Keep context, money, career and work in one local folder. Record what actually
happened, review it, and decide what to do next. Share the software; keep your data.
The core runs without an AI account, API key, server or paid dependency.

## Try it in five minutes

Requires Python 3.9+. From this source folder:

```sh
python3 -m lifekit --workspace ./workspace init --currency INR
python3 -m lifekit --workspace ./workspace doctor
python3 -m lifekit --workspace ./workspace checkin --sleep 7 --gym yes --prep 30
python3 -m lifekit --workspace ./workspace spend 120 --category food
python3 -m lifekit --workspace ./workspace report
```

Open the printed report path. Edit `workspace/personal/rules.md` with your preferences
and constraints, then add dated context to the domain folders. `workspace/` is ignored
by Git. You can choose an absolute folder outside the repository; reuse the same
`--workspace` path for every command. Init refuses nonempty destinations.

Optionally install the CLI in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
life-kit --workspace ./workspace status
```

On Windows use `python` and activate with `.venv\Scripts\Activate.ps1` in PowerShell.
Activation is unnecessary when running `python -m lifekit` directly from source.

## What works today

| Feature | Behavior |
|---|---|
| Workspace setup | Blank personal, finance, career and work context |
| Local doctor | Config/event validation and optional CLI detection |
| Check-ins | Explicit sleep, gym and prep self-reports |
| Spending | Exact decimal amounts in your chosen currency |
| Action/outcome log | Each outcome links to one specific action ID |
| Resume fingerprint | Hashes the actual file used without uploading it |
| Review | Local Markdown report, with missing data visibly unknown |
| Agent workflow | Generated workspace AGENTS.md and portable review skill |

The core does **not** connect Gmail, calendars, banks, shopping, work systems or
Telegram. Those need per-user authentication and adapters. See the
[integration guide](docs/integrations.md) and [roadmap](docs/roadmap.md).
This is an early reusable starter, not the full automation of its private origin.

## Learn from outcomes

Record an action only after it happened:

```sh
python3 -m lifekit --workspace ./workspace action --channel email --target demo-role --variant specific-role
```

Use the printed ID as EVENT_ID:

```sh
python3 -m lifekit --workspace ./workspace outcome EVENT_ID reply --evidence "self-report: recruiter replied"
```

This sends no email. Receipts, auto replies, accepts, human replies, referrals,
assessments, interviews and offers remain distinct. Repeated outcomes for the same
stage/action count once. Use `--request-id` for retry deduplication. For a real
application, `action --resume PATH` stores its SHA256 locally. Missing old resume
versions are never guessed.

## Use with an assistant

Ask your local assistant to read the private workspace's AGENTS.md and rules, then
help with a specific domain. Use [life-review](skills/life-review/SKILL.md) if it supports
skills. The CLI never starts an AI session. An AI provider has its own data handling:
local storage does not mean files stay local once a remote model reads them.

```text
lifekit/       Local CLI and storage
skills/        Portable assistant workflow
examples/      Fictional demo
workspace/     Your private data, generated locally and ignored
```

[Getting started](docs/getting-started.md) · [Architecture](docs/architecture.md) ·
[GitHub sharing](docs/publishing.md) · [Contributing](CONTRIBUTING.md)

Run `python3 -m unittest discover -s tests -v` and `python3 scripts/check_public.py`.
MIT licensed. No telemetry, background jobs or external actions are installed.
