# Working on Life Kit

This repository contains generic source and fictional examples. User workspaces,
reports, sessions and personal records never belong in commits.

Read README.md and relevant docs. Keep the core standard-library only, Python 3.9+.
State paths come from --workspace. Never assume a username, employer, timezone,
currency or account. Use temporary workspaces for tests. Run the tests and public
source check documented in README. Preserve exact money, explicit outcome IDs,
unknown-vs-zero and self-reported-vs-observed distinctions.

Local setup does not authorize messages, applications, purchases or publishing.
Connectors are optional and must distinguish configuration, authentication and a
verified live read. No account is connected by default. Do not copy private data
or configuration into this repository, even for fixtures or screenshots.

Templates in lifekit/templates/ (skills, context files, runner prompts) are public: write them
generically, with no names, employers, amounts, paths or accounts from anyone's real workspace.
Template text uses string.Template, so a literal dollar sign is written $$. After changing
lifekit/questions.py, regenerate the guide: python3 -m lifekit guide > docs/setup-guide.md.
Runners, verification and Telegram must stay read-only and must never send, submit or buy.
