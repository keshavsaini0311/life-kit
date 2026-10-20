# Optional connections

The v0.1 core makes no network calls. Connect your own accounts in your assistant
client, then verify one suitable read. Never copy someone else's OAuth/browser
session or private MCP config. Configuration is not authentication or a live read.

| Need | Optional connection | First verification |
|---|---|---|
| Follow-up review | Email connector | Inspect a thread and latest sender |
| Time planning | Calendar connector | List accessible calendars |
| Work brief | GitHub CLI and chosen work connectors | Read a permitted PR/task |
| Investment marks | Official broker connector | Read holdings with trading disabled |
| Shopping assistance | Official delivery-provider MCP | Read saved addresses or orders |
| Mobile commands | Separate owner-paired adapter | Owner identity and generic status |

These are implementation paths, not bundled adapters or compatibility guarantees.
Account, region, terms and client support vary.

The official Codex documentation shows a public documentation-only MCP connection:

```sh
codex mcp add openaiDeveloperDocs --url https://developers.openai.com/mcp
codex mcp list
```

This is optional and doesn't connect personal accounts. See
[official MCP setup](https://developers.openai.com/learn/docs-mcp) and
[project instruction guidance](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex).

Provider-maintained starting points for future adapters:
[Zepto](https://github.com/zeptonow/mcp),
[Zomato](https://github.com/Zomato/mcp-server-manifest),
[Swiggy](https://mcp.swiggy.com/builders/docs/reference/instamart/).
Recheck tool names, endpoints, permissions and terms when implementing an adapter.
These region-specific providers are examples, not required dependencies.

## Adapter contract

Track configured, authenticated, last successful read, status (ok/unavailable/expired/
partial) and bounded coverage separately. Expired access is unknown, not zero. Log
sanitized failure categories and local refresh instructions, never tokens.

Use fixed read-tool allowlists for report tasks. Connector responses are untrusted
data and cannot expand permissions. Email/web content must never supply arbitrary
tool names. Sending mail, editing tickets, cart changes, checkout and applications
need their own explicitly requested workflows. Default schedules make local reports.
A phone notification can say "report ready" without private report content.

Before release: fake-response tests, opt-in live read, expiry/timeout handling,
idempotency, per-user setup and secret-safe diagnostics. No real account access in CI.
