"""Write per-assistant MCP config from the catalog and record verified reads.

Configured, authenticated and last verified read are separate facts in .local/connections.json.
Secrets live in .local/secrets.json; config files only reference environment variables.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from . import catalog, core

STATUS = ".local/connections.json"
ID = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


def entry(root, conn_id):
    """Catalog entry, or the user's custom server stored in life.json."""
    for item in catalog.CONNECTIONS:
        if item["id"] == conn_id and item["source"] != "custom":
            return item
    custom = (core.load(root)[1].get("connections") or {}).get(conn_id)
    if custom and custom.get("server"):
        return dict(catalog.CUSTOM, id=conn_id, title=custom.get("title", conn_id), server=custom["server"],
                    read_tools=custom.get("read_tools", []), verify=custom.get("verify"))
    raise ValueError("Unknown connection: " + conn_id + ". See `life-kit connect list`.")


def _env_names(item):
    return [s["env"] for s in item.get("secrets", [])] + item["server"].get("env_pass", [])


def claude_server(item):
    server = item["server"]
    if server["type"] == "account":
        return None
    if server["type"] == "http":
        result = {"type": "http", "url": server["url"]}
        if server.get("bearer_env"):
            result["headers"] = {"Authorization": "Bearer ${" + server["bearer_env"] + "}"}
        return result
    result = {"command": server["command"], "args": list(server.get("args", []))}
    if _env_names(item):
        result["env"] = {name: "${" + name + "}" for name in _env_names(item)}
    return result


def codex_values(item):
    """Key/value pairs for [mcp_servers.<id>] (also used as -c overrides)."""
    server = item["server"]
    if server["type"] == "account":
        return None
    values = {"url": server["url"]} if server["type"] == "http" else {"command": server["command"], "args": list(server.get("args", []))}
    if server.get("bearer_env"):
        values["bearer_token_env_var"] = server["bearer_env"]
    if server["type"] == "stdio" and _env_names(item):
        values["env_vars"] = _env_names(item)
    if item.get("read_tools"):
        values["enabled_tools"] = list(item["read_tools"])
    return values


def _toml(value):
    return json.dumps(value)  # JSON strings/arrays of strings are valid TOML


def codex_overrides(item):
    values = codex_values(item) or {}
    args = []
    for key, value in values.items():
        args += ["-c", "mcp_servers." + item["id"] + "." + key + "=" + _toml(value)]
    return args


def tool_name(item, tool):
    if item["server"]["type"] == "account":
        return "mcp__claude_ai_" + item["server"]["name"].replace(" ", "_") + "__" + tool
    return "mcp__" + item["id"] + "__" + tool


def enabled(root):
    return list((core.load(root)[1].get("connections") or {}).keys())


def env(root):
    """Environment for assistant subprocesses: secrets mapped to the variables config files reference."""
    result = dict(os.environ)
    for conn_id in enabled(root):
        for secret in entry(root, conn_id).get("secrets", []):
            value = core.secret(root, secret["name"])
            if value:
                result[secret["env"]] = value
    return result


def write_configs(root, ids, custom=None):
    """Enable connections and add them to .mcp.json / .codex/config.toml without touching other servers."""
    root, _ = core.load(root)
    custom = custom or {}
    known = {c["id"] for c in catalog.CONNECTIONS if c["source"] != "custom"}
    for conn_id in ids:
        if conn_id in custom:
            if not ID.match(conn_id) or conn_id in known:
                raise ValueError("Custom connection id must be a new lowercase name like my-server.")
        elif conn_id not in known:
            entry(root, conn_id)  # raises unless it is an existing custom server

    def change(config):
        stored = config.setdefault("connections", {})
        for conn_id in ids:
            stored.setdefault(conn_id, custom.get(conn_id, {}))
    core.update_config(root, change)

    written = []
    mcp_path = root / ".mcp.json"
    data = json.loads(mcp_path.read_text(encoding="utf-8")) if mcp_path.is_file() else {"mcpServers": {}}
    servers = data.setdefault("mcpServers", {})
    toml_path = root / ".codex/config.toml"
    toml = toml_path.read_text(encoding="utf-8") if toml_path.is_file() else ""
    for conn_id in ids:
        item = entry(root, conn_id)
        server = claude_server(item)
        if server and conn_id not in servers:
            servers[conn_id] = server
        values = codex_values(item)
        if values and "[mcp_servers." + conn_id + "]" not in toml:
            block = "\n[mcp_servers." + conn_id + "]\n" + "".join(k + " = " + _toml(v) + "\n" for k, v in values.items())
            toml = toml.rstrip("\n") + ("\n" if toml.strip() else "") + block
    core.private_write(mcp_path, core.json_text(data))
    written.append(".mcp.json")
    if toml.strip():
        core.private_write(toml_path, toml.lstrip("\n"))
        written.append(".codex/config.toml")
    lines = ["# Generated by life-kit. Secrets: keep private, never commit or share."]
    for conn_id in enabled(root):
        for secret in entry(root, conn_id).get("secrets", []):
            value = core.secret(root, secret["name"])
            if value:
                lines.append("export " + secret["env"] + "=" + shlex.quote(value))
    core.private_write(root / ".local/env.sh", "\n".join(lines) + "\n")
    return written


def status(root):
    path = Path(root) / STATUS
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _record(root, conn_id, **fields):
    with core.locked(root):
        data = status(root)
        data[conn_id] = dict(data.get(conn_id, {}), configured=True, **fields)
        core.private_write(Path(root) / STATUS, core.json_text(data))
    return data[conn_id]


VERIFY_PROMPT = ("Call the MCP tool {tool} exactly once with arguments {args}. Call no other tool. "
                 "Then reply with one word only: OK if it returned data, AUTH if it failed because of "
                 "login, authentication or permission, FAIL for anything else.")


def verify(root, conn_id, assistant=None, run=subprocess.run, timeout=180):
    """One real read through the assistant, restricted to that single read tool."""
    root, config = core.load(root)
    if conn_id not in enabled(root):
        raise ValueError(conn_id + " is not configured. Run `life-kit connect add " + conn_id + "` first.")
    item = entry(root, conn_id)
    if not item.get("verify"):
        return _record(root, conn_id, status="unverified", error="no-verify-tool")
    assistant = assistant or (item["headless"][0] if item["headless"] else config.get("primary_assistant") or "claude")
    if assistant not in item["headless"]:
        raise ValueError(item["title"] + " can be read unattended only through: " + ", ".join(item["headless"]))
    prompt = VERIFY_PROMPT.format(tool=tool_name(item, item["verify"]["tool"]) if assistant == "claude" else item["verify"]["tool"],
                                  args=json.dumps(item["verify"].get("args", {})))
    answer, output = None, None
    try:
        if assistant == "claude":
            argv = ["claude", "-p", "--output-format", "json", "--max-turns", "3",
                    "--allowedTools", tool_name(item, item["verify"]["tool"])]
            if claude_server(item) and (root / ".mcp.json").is_file():
                argv += ["--mcp-config", str(root / ".mcp.json")]
            result = run(argv + [prompt], cwd=str(root), env=env(root), capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                answer = str(json.loads(result.stdout).get("result", ""))
        else:
            fd, output = tempfile.mkstemp(prefix=".verify-", dir=str(root / ".local"))
            os.close(fd)
            argv = ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--cd", str(root), "--sandbox", "read-only",
                    "-c", "features.apps=" + ("true" if item["server"]["type"] == "account" else "false")]
            argv += codex_overrides(item) + ["--output-last-message", output, prompt]
            result = run(argv, cwd=str(root), env=env(root), capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                answer = Path(output).read_text(encoding="utf-8")
    except FileNotFoundError:
        return _record(root, conn_id, status="unavailable", error="absent", checked_at=core.timestamp())
    except subprocess.TimeoutExpired:
        return _record(root, conn_id, status="unavailable", error="timeout", checked_at=core.timestamp())
    except ValueError:  # unparseable assistant output
        answer = None
    finally:
        if output and os.path.exists(output):
            os.unlink(output)
    word = (answer or "").strip().split()[0].strip(".").upper() if (answer or "").strip() else ""
    now = core.timestamp()
    if word == "OK":
        return _record(root, conn_id, status="ok", authenticated=True, last_read_at=now, checked_at=now,
                       error=None, assistant=assistant)
    if word == "AUTH":
        return _record(root, conn_id, status="expired", authenticated=False, last_read_at=None, checked_at=now,
                       error="auth", assistant=assistant)
    previous = status(root).get(conn_id, {})
    return _record(root, conn_id, status="unavailable", authenticated=previous.get("authenticated"),
                   last_read_at=previous.get("last_read_at"), checked_at=now, error="tool", assistant=assistant)
