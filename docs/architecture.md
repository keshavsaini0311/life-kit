# Architecture

Shareable source and private runtime data are separate.

```mermaid
flowchart LR
  U[You] --> W[life-kit setup]
  W --> C[Private workspace]
  W --> S[Skills .agents/skills]
  W --> M[.mcp.json / .codex/config.toml]
  A[Claude Code / Codex] --> S
  A --> M
  M -. read-only .-> X[Connected services]
  O[OS scheduler] --> R[Runners]
  R --> A
  R --> L[maintain: ledger, learning]
  L --> C
  T[Telegram bot] --> R
  R --> P[Local reports]
```

| Module | Responsibility |
|---|---|
| `core.py` | Workspace config (schema 2), event log, locks, atomic writes, secrets |
| `questions.py`, `wizard.py` | The explained question table, resumable setup, summary |
| `render.py`, `templates/` | Context files and skills; never overwrites user edits |
| `catalog.py`, `connections.py` | Connection catalog, per-assistant config, verified reads |
| `ledger.py`, `learning.py`, `maintain.py` | Bank import, monthly ledgers, learning report, freshness |
| `runners.py`, `schedule.py` | Bounded read-only jobs and OS scheduler install |
| `telegram.py` | Owner-paired phone channel |

The core itself makes no network calls. Only connection verification, runners and the
Telegram service start other programs or talk to the network, and only when you ask.

core.py validates and stores observations; cli.py parses arguments. The core is useful
without AI; assistants add reading, drafting and review on top.

Events have unique IDs and UTC timestamps. Reports use local calendar days and exclude
future events. Money uses decimal strings. Outcomes reference exact action IDs and
stage counts deduplicate repeated outcomes for an action. Stages aren't additive
people counts. Missing outcomes are unknown and rates don't establish causality.
Resume fingerprints identify bytes, not quality, delivery or application success.

A cross-process lock serializes writes. Atomic replacement keeps the previous complete
file on interruption. The single-user store rewrites the log when appending; very large
histories need a different approach. Request IDs deduplicate identical retries and
reject reused IDs with different content. `life-kit migrate` upgrades a v1 config. Correction events and
lock timeouts are future work.

POSIX files are created owner-only; Windows relies on account/directory ACLs. Files
are not encrypted at rest. Use a trusted user account and disk. Local storage doesn't
guarantee local-only AI processing if you let a remote assistant read files.
