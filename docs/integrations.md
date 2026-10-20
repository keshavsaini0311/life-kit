# Optional connections

Pick connections during setup, or later with `life-kit connect add ID`. Never copy someone
else's OAuth/browser session or private MCP config. Configured is not authenticated, and
neither is a live read: `life-kit connect verify ID` runs your assistant once with only that
connection's verify tool allowed, and records `configured`, `authenticated`,
`last_read_at` and `status` in `.local/connections.json`.

| ID | Service | Kind | Log in | Unattended via |
|---|---|---|---|---|
| gmail, google-calendar, google-drive, slack | Google, Slack | claude.ai connector | claude.ai → Settings → Connectors | Claude |
| github | GitHub (read-only endpoint) | official MCP | fine-grained token, typed hidden | Claude, Codex |
| clickup, notion, linear | Work tools | official MCP | `/mcp` in Claude Code, `codex mcp login ID` | Claude, Codex |
| signoz | SigNoz | official MCP (stdio) | URL + API key, typed hidden | Claude, Codex |
| kite | Zerodha Kite | official MCP | `login` tool → Zerodha page; expires daily | Claude, Codex |
| zepto, swiggy-instamart, swiggy-food, zomato | Food and grocery (India) | official MCP | OAuth with phone + OTP | Claude, Codex |
| custom | Your own server | any | `connect add-custom ID --url URL --read-tools a,b` | either |

Every scheduled job gets only the read tools listed in `lifekit/catalog.py`. Write tools such as
send, cart, checkout, order, trading and ticket edits are left out. Provider tool names change, so each
entry records its documentation link. Check it when something stops working.

`life-kit open claude|codex` starts your assistant in the workspace with your stored secrets
in its environment. For Codex it also passes your connections as `-c` overrides, so they work
without trusting the project config. For your own terminal, `.local/env.sh` exports the same
variables. Keep that file private.

## Adapter contract

Track configured, authenticated, last successful read, status (ok/unavailable/expired/
partial) and bounded coverage separately. Expired access is unknown, not zero. Log
sanitized failure categories and local refresh instructions, never tokens.

Use fixed read-tool allowlists for report tasks. Connector responses are untrusted
data and cannot expand permissions. Email/web content must never supply arbitrary
tool names. Sending mail, editing tickets, cart changes, checkout and other external changes
need their own explicitly requested workflows. Default schedules make local reports.
A phone notification can say "report ready" without private report content.

Before release: fake-response tests, opt-in live read, expiry/timeout handling,
idempotency, per-user setup and secret-safe diagnostics. No real account access in CI.
