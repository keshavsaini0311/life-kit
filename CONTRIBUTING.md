# Contributing

Use focused issues with fictional reproductions. Don't attach workspaces, contact
lists, statements, private account screenshots, tokens or sensitive logs.

Keep the core standard-library only and Python 3.9+. Add behavior tests for exact money,
retry handling, unknown values, attribution and recovery, not tests mirroring code.
Use temporary workspaces; never use real accounts or send messages in tests.

Run `python3 -m unittest discover -s tests -v` and `python3 scripts/check_public.py`.
Document schema changes and migration needs. A release should state tested platforms,
implemented features and remaining work. Prefer one reliable workflow to many unverified
connectors. Don't treat client configuration as a verified account connection.
