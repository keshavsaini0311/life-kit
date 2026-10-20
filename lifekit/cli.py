"""Command-line interface; all writes stay in the explicitly selected workspace."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import getpass
import os
import subprocess

from . import catalog, connections, core, questions, wizard


def main(argv=None):
    parser = argparse.ArgumentParser(description="Life Kit: a local workspace for your own routines.")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"), help="Private data folder (default: ./workspace)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a new private workspace with blank context")
    init.add_argument("--currency", default="INR")
    p = sub.add_parser("setup", help="Guided setup: explained questions, resumable, never overwrites your edits")
    p.add_argument("--answers", type=Path, help="JSON answers file; runs without prompting")
    sub.add_parser("guide", help="Print every setup question with why/example/skip (Markdown)")
    conn = sub.add_parser("connect", help="Optional read-only connections (list, add, verify, status)")
    csub = conn.add_subparsers(dest="action", required=True)
    csub.add_parser("list")
    csub.add_parser("status")
    p = csub.add_parser("add")
    p.add_argument("ids", nargs="+")
    p = csub.add_parser("add-custom", help="Your own MCP server")
    p.add_argument("id")
    p.add_argument("--url")
    p.add_argument("--command", dest="server_command", nargs=argparse.REMAINDER)
    p.add_argument("--read-tools", default="", help="Comma-separated tools runners may call")
    p.add_argument("--verify-tool")
    p = csub.add_parser("verify")
    p.add_argument("id")
    p.add_argument("--assistant", choices=("claude", "codex"))
    sub.add_parser("plugins", help="Recommended Claude Code plugins and their install commands")
    p = sub.add_parser("open", help="Start Claude Code or Codex in the workspace with your connections")
    p.add_argument("assistant", choices=("claude", "codex"))
    sub.add_parser("migrate", help="Upgrade life.json to the current schema; keeps a backup")
    sub.add_parser("doctor", help="Check local files; does not authenticate or contact providers")
    for command in ("status", "report"):
        p = sub.add_parser(command)
        p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("checkin")
    p.add_argument("--sleep", type=float)
    p.add_argument("--gym", choices=("yes", "no", "rest"))
    p.add_argument("--prep", type=int, help="Self-reported minutes")
    p.add_argument("--request-id", help="Retry key; same key + content writes once")
    p = sub.add_parser("spend")
    p.add_argument("amount")
    p.add_argument("--category", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--request-id")
    p = sub.add_parser("action", help="Record an action that actually occurred; does not perform it")
    p.add_argument("--domain", choices=core.DOMAINS, default="career")
    p.add_argument("--channel", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--variant", default="unrecorded")
    p.add_argument("--resume", type=Path, help="Hash the actual file used; never uploads it")
    p.add_argument("--request-id")
    p = sub.add_parser("outcome")
    p.add_argument("action_id")
    p.add_argument("stage", choices=core.STAGES)
    p.add_argument("--evidence", required=True, help="Local evidence reference or explicit self-report")
    p.add_argument("--request-id")
    args = parser.parse_args(argv)
    try:
        root = args.workspace
        if args.command == "init":
            print("Created private workspace: " + str(core.init(root, args.currency)))
        elif args.command == "setup":
            wizard.run(root, answers_file=args.answers, interactive=args.answers is None)
            print("\nSetup saved in " + str(root.expanduser().resolve()))
        elif args.command == "guide":
            print(questions.guide_markdown(), end="")
        elif args.command == "connect":
            return connect(root, args)
        elif args.command == "plugins":
            for plugin in catalog.PLUGINS:
                print(plugin["id"] + ": " + plugin["why"] + "\n    " + plugin["install"])
        elif args.command == "open":
            return open_assistant(root, args.assistant)
        elif args.command == "migrate":
            print("Upgraded. Previous config kept at: " + str(core.migrate(root)))
        elif args.command == "doctor":
            root, _ = core.load(root)
            count = len(core.events(root))
            for domain in core.DOMAINS:
                if not (root / domain / "context.md").is_file():
                    raise ValueError("Missing context file for " + domain)
            print("Local schema and event log valid (" + str(count) + " records).")
            print("Optional tools: " + ", ".join(n + "=" + ("installed" if shutil.which(n) else "absent") for n in ("codex", "claude", "gh", "node")))
            print("Provider authentication/network access: NOT CHECKED.")
        elif args.command == "status":
            print(core.json_text(core.snapshot(root, args.days)), end="")
        elif args.command == "report":
            print("Local report saved: " + str(core.report(root, args.days)))
        else:
            if args.command == "checkin":
                event = core.checkin(root, args.sleep, args.gym, args.prep, args.request_id)
            elif args.command == "spend":
                event = core.spend(root, args.amount, args.category, args.note, args.request_id)
            elif args.command == "action":
                event = core.action(root, args.domain, args.channel, args.target, args.variant, args.resume, args.request_id)
            else:
                event = core.outcome(root, args.action_id, args.stage, args.evidence, args.request_id)
            print("Saved locally: " + event["id"])
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Answers so far are saved; run setup again to continue.", file=sys.stderr)
        return 130
    except (ValueError, OSError, UnicodeError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1


def connect(root, args):
    if args.action == "list":
        for item in catalog.CONNECTIONS:
            print(item["id"] + " — " + item["title"] + " [" + item["source"] + "] for " + ", ".join(item["domains"]))
        print("custom — your own server: life-kit connect add-custom ID --url URL")
        return 0
    if args.action == "status":
        records = connections.status(root)
        for conn_id in connections.enabled(root):
            r = records.get(conn_id, {})
            print(conn_id + ": configured; " + (r.get("status") or "not verified")
                  + ("; last read " + r["last_read_at"] if r.get("last_read_at") else ""))
        return 0
    if args.action == "verify":
        record = connections.verify(root, args.id, args.assistant)
        print(args.id + ": " + record["status"] + ("" if record["status"] == "ok" else " (" + str(record.get("error")) + ")"))
        return 0 if record["status"] == "ok" else 1
    if args.action == "add-custom":
        if bool(args.url) == bool(args.server_command):
            raise ValueError("Give exactly one of --url or --command.")
        server = {"type": "http", "url": args.url} if args.url else {"type": "stdio", "command": args.server_command[0], "args": args.server_command[1:]}
        tools = [t.strip() for t in args.read_tools.split(",") if t.strip()]
        custom = {"server": server, "read_tools": tools,
                  "verify": {"tool": args.verify_tool, "args": {}} if args.verify_tool else None}
        connections.write_configs(root, [args.id], custom={args.id: custom})
        ids = [args.id]
    else:
        ids = args.ids
        for conn_id in ids:
            for secret in connections.entry(root, conn_id).get("secrets", []):
                if not core.secret(root, secret["name"]):
                    value = getpass.getpass(secret["prompt"] + " (hidden, Enter to skip): ").strip()
                    if value:
                        core.save_secret(root, secret["name"], value)
        connections.write_configs(root, ids)
    for conn_id in ids:
        item = connections.entry(root, conn_id)
        print(item["title"] + " configured (not yet verified). To log in:")
        for step in item["login"]:
            print("  - " + step)
        print("  Then: life-kit --workspace " + str(root) + " connect verify " + conn_id)
    return 0


def open_assistant(root, assistant):
    root, _ = core.load(root)
    argv = [assistant]
    if assistant == "codex":
        for conn_id in connections.enabled(root):
            argv += connections.codex_overrides(connections.entry(root, conn_id))
    env = connections.env(root)
    if os.name == "nt":
        return subprocess.call(argv, cwd=str(root), env=env)
    os.chdir(str(root))
    os.execvpe(assistant, argv, env)
