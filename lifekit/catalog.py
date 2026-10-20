"""Optional connections and Claude Code plugins offered during setup.

Each connection: id, title, domains it helps, source (official|community|account|custom), docs,
server (http: url [+bearer_env] | stdio: command, args [+env_pass] | account: claude.ai connector name),
secrets (hidden prompts stored in .local/secrets.json, exposed to assistants as env vars),
login steps, read_tools (the only tools runners may call), verify (one read), headless
(assistants that can read it unattended). Provider tool names drift: re-check `docs` when updating.
"""

def _c(id, title, domains, source, docs, server, login, read_tools, verify=None, headless=("claude", "codex"),
       secrets=(), note=""):
    return dict(id=id, title=title, domains=list(domains), source=source, docs=docs, server=server,
                login=list(login), read_tools=list(read_tools), verify=verify, headless=list(headless),
                secrets=list(secrets), note=note)


CLAUDE_ACCOUNT_LOGIN = ["Open claude.ai → Settings → Connectors, connect {name} with your own account.",
                        "Claude Code uses the same claude.ai login, so no file changes are needed.",
                        "Codex: use the ChatGPT app's own {name} connector if you want it there (not used by runners)."]


def _account(id, title, domains, docs, name, read_tools, verify):
    return _c(id, title, domains, "account", docs, {"type": "account", "name": name},
              [s.format(name=name) for s in CLAUDE_ACCOUNT_LOGIN], read_tools, verify, headless=("claude",))


CONNECTIONS = [
    _account("gmail", "Gmail", ["career", "finance", "personal"], "https://support.claude.com/en/articles/10166901",
             "Gmail", ["search_threads", "get_thread", "get_message", "list_labels"], {"tool": "list_labels", "args": {}}),
    _account("google-calendar", "Google Calendar", ["personal", "career", "work"],
             "https://support.claude.com/en/articles/10166901", "Google Calendar",
             ["list_calendars", "list_events", "get_event"], {"tool": "list_calendars", "args": {}}),
    _account("google-drive", "Google Drive", ["career", "personal"], "https://support.claude.com/en/articles/10166901",
             "Google Drive", ["search", "fetch"], {"tool": "search", "args": {"query": "resume"}}),
    _account("slack", "Slack", ["work"], "https://support.claude.com/en/articles/11506255", "Slack",
             ["slack_read_user_profile", "slack_search_channels", "slack_read_channel", "slack_read_thread",
              "slack_search_public"], {"tool": "slack_read_user_profile", "args": {}}),

    _c("github", "GitHub", ["work", "career"], "official", "https://github.com/github/github-mcp-server",
       {"type": "http", "url": "https://api.githubcopilot.com/mcp/readonly", "bearer_env": "LIFEKIT_GITHUB_TOKEN"},
       ["Create a fine-grained personal access token at https://github.com/settings/personal-access-tokens "
        "with read-only access to the repositories you want.",
        "Paste it at the hidden prompt. Alternatively keep using the `gh` CLI (`gh auth login`)."],
       ["get_me", "search_repositories", "list_issues", "list_pull_requests", "get_pull_request", "get_file_contents"],
       {"tool": "get_me", "args": {}},
       secrets=[{"name": "github_token", "env": "LIFEKIT_GITHUB_TOKEN", "prompt": "GitHub token (read-only)"}]),
    _c("clickup", "ClickUp", ["work"], "official", "https://developer.clickup.com/docs/connect-an-ai-assistant-to-clickups-mcp-server",
       {"type": "http", "url": "https://mcp.clickup.com/mcp"},
       ["Claude Code: start `claude` in your workspace, run /mcp, choose clickup, Authenticate.",
        "Codex: run `codex mcp login clickup` in your workspace."],
       ["clickup_get_workspace_hierarchy", "clickup_filter_tasks", "clickup_get_task", "clickup_search"],
       {"tool": "clickup_get_workspace_hierarchy", "args": {}}),
    _c("notion", "Notion", ["work", "personal"], "official", "https://developers.notion.com/docs/mcp",
       {"type": "http", "url": "https://mcp.notion.com/mcp"},
       ["Claude Code: /mcp → notion → Authenticate.", "Codex: `codex mcp login notion`."],
       ["notion-search", "notion-fetch", "notion-get-self"], {"tool": "notion-get-self", "args": {}}),
    _c("linear", "Linear", ["work"], "official", "https://linear.app/docs/mcp",
       {"type": "http", "url": "https://mcp.linear.app/mcp/readonly"},
       ["Claude Code: /mcp → linear → Authenticate.", "Codex: `codex mcp login linear`."],
       ["list_issues", "get_issue", "list_teams", "list_projects"], {"tool": "list_teams", "args": {}}),
    _c("signoz", "SigNoz", ["work"], "official", "https://github.com/SigNoz/signoz-mcp-server",
       {"type": "stdio", "command": "signoz-mcp-server", "args": []},
       ["Install signoz-mcp-server (see docs) so the command is on your PATH. SigNoz Cloud users can "
        "instead add its hosted endpoint as a custom connection.",
        "Create an API key in SigNoz settings; paste your SigNoz URL and the key at the prompts."],
       ["signoz_list_services", "signoz_search_logs", "signoz_list_alerts", "signoz_get_service_top_operations"],
       {"tool": "signoz_list_services", "args": {}},
       secrets=[{"name": "signoz_url", "env": "SIGNOZ_URL", "prompt": "SigNoz URL (https://...)"},
                {"name": "signoz_api_key", "env": "SIGNOZ_API_KEY", "prompt": "SigNoz API key"}]),
    _c("kite", "Zerodha Kite (read-only)", ["finance"], "official", "https://github.com/zerodha/kite-mcp-server",
       {"type": "http", "url": "https://mcp.kite.trade/mcp"},
       ["If the direct connection is blocked, Zerodha's docs show a fallback: `npx mcp-remote https://mcp.kite.trade/mcp`.",
        "Ask your assistant to call the Kite `login` tool and open the link it returns; "
        "sign in on Zerodha's site. Sessions expire daily; expired means unknown, not zero."],
       ["login", "get_profile", "get_holdings", "get_mf_holdings", "get_positions", "get_margins"],
       {"tool": "get_profile", "args": {}},
       note="Trading and order tools are excluded by the read-only allowlist."),
    _c("zepto", "Zepto", ["personal", "finance"], "official", "https://github.com/zeptonow/mcp",
       {"type": "http", "url": "https://mcp.zepto.co.in/mcp"},
       ["Claude Code: /mcp → zepto → Authenticate (Indian mobile number + OTP).", "Codex: `codex mcp login zepto`."],
       ["list_saved_addresses", "list_order_history", "get_order_detail", "get_past_order_items", "search_products"],
       {"tool": "list_saved_addresses", "args": {}},
       note="Cart, checkout and payment tools are excluded."),
    _c("swiggy-instamart", "Swiggy Instamart", ["personal", "finance"], "official",
       "https://mcp.swiggy.com/builders/docs/reference/instamart/",
       {"type": "http", "url": "https://mcp.swiggy.com/im"},
       ["Claude Code: /mcp → swiggy-instamart → Authenticate.", "Codex: `codex mcp login swiggy-instamart`."],
       ["get_addresses", "get_orders", "track_order", "search_products"], {"tool": "get_addresses", "args": {}},
       note="Cart, checkout and payment tools are excluded."),
    _c("swiggy-food", "Swiggy Food", ["personal", "finance"], "official", "https://mcp.swiggy.com/builders/docs/",
       {"type": "http", "url": "https://mcp.swiggy.com/food"},
       ["Claude Code: /mcp → swiggy-food → Authenticate.", "Codex: `codex mcp login swiggy-food`."],
       ["get_addresses", "get_orders", "track_order", "search_restaurants"], {"tool": "get_addresses", "args": {}},
       note="Cart and order placement tools are excluded."),
    _c("zomato", "Zomato", ["personal", "finance"], "official", "https://github.com/Zomato/mcp-server-manifest",
       {"type": "http", "url": "https://mcp-server.zomato.com/mcp"},
       ["Claude Code: /mcp → zomato → Authenticate.", "Codex: `codex mcp login zomato`."],
       ["get_saved_addresses_for_user", "get_order_history", "get_order_tracking_info", "get_restaurants_for_keyword"],
       {"tool": "get_saved_addresses_for_user", "args": {}},
       note="Cart, checkout and phone-binding tools are excluded. Zomato marks its server as for testing."),
    _c("linkedin", "LinkedIn (community server)", ["career"], "community", "https://github.com/stickerdaniel/linkedin-mcp-server",
       {"type": "stdio", "command": "uvx", "args": ["mcp-server-linkedin@latest"]},
       ["Community-maintained, not LinkedIn's. Automated access may break LinkedIn's terms; use at your own risk.",
        "Follow the server's README to sign in. Runners never send messages or connection requests."],
       ["get_my_profile", "get_person_profile", "get_company_profile", "search_jobs", "get_job_details"],
       {"tool": "get_my_profile", "args": {}}, headless=("claude",)),
]

CUSTOM = _c("custom", "Your own MCP server", ["work", "career", "finance", "personal"], "custom",
            "https://modelcontextprotocol.io/docs/getting-started/intro", {"type": "http", "url": ""},
            ["Use the server's own instructions to authenticate (`/mcp` in Claude Code, `codex mcp login ID`)."],
            [], None)

PLUGINS = [
    dict(id="superpowers", why="Structured brainstorming, planning, TDD and debugging workflows.",
         install="claude plugin install superpowers@claude-plugins-official"),
    dict(id="context7", why="Fetches current library documentation instead of guessing APIs.",
         install="claude plugin install context7@claude-plugins-official"),
    dict(id="github", why="GitHub integration for PRs and issues from Claude Code.",
         install="claude plugin install github@claude-plugins-official"),
    dict(id="code-review", why="Reviews diffs and pull requests for bugs.",
         install="claude plugin install code-review@claude-plugins-official"),
    dict(id="skill-creator", why="Create and improve your own skills, like the ones in this workspace.",
         install="claude plugin install skill-creator@claude-plugins-official"),
    dict(id="frontend-design", why="Better visual design when building pages or dashboards.",
         install="claude plugin install frontend-design@claude-plugins-official"),
]
