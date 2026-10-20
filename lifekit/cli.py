"""Command-line interface; all writes stay in the explicitly selected workspace."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import getpass
import os
import subprocess

from . import catalog, connections, core, learning, ledger, maintain, questions, runners, schedule, telegram, wizard


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:  # a cp1252 Windows console cannot print arrows or dashes; show "?" instead of crashing
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
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
    led = sub.add_parser("ledger", help="Bank CSV import and generated monthly ledgers")
    lsub = led.add_subparsers(dest="action", required=True)
    lsub.add_parser("import", help="Import finance/inbox/*.csv and post rows matching finance/rules.json")
    p = lsub.add_parser("render")
    p.add_argument("month", nargs="?", help="YYYY-MM (default: this month)")
    sub.add_parser("learn", help="Write the learning report (rates, follow-ups) from the event log")
    sub.add_parser("maintain", help="Import, rebuild ledgers and learning, list stale data")
    p = sub.add_parser("run", help="Run one scheduled job now (once per scheduled slot unless --force)")
    p.add_argument("runner", choices=sorted(runners.RUNNERS))
    p.add_argument("--force", action="store_true")
    sched = sub.add_parser("schedule", help="Install, change or remove scheduled jobs (your OS scheduler)")
    ssub = sched.add_subparsers(dest="action", required=True)
    p = ssub.add_parser("install")
    p.add_argument("--dry-run", action="store_true", help="Show what would be written; change nothing")
    ssub.add_parser("remove")
    ssub.add_parser("status")
    p = ssub.add_parser("set", help="e.g. schedule set work-brief 08:30 --days weekdays")
    p.add_argument("runner", choices=sorted(runners.RUNNERS))
    p.add_argument("times", help="HH:MM or HH:MM,HH:MM")
    p.add_argument("--days", default=None, help="daily, weekdays or mon..sun")
    p.add_argument("--assistant", choices=("claude", "codex"))
    p = ssub.add_parser("off")
    p.add_argument("runner", choices=sorted(runners.RUNNERS))
    tg = sub.add_parser("telegram", help="Private phone channel: setup (pair), check, run (foreground service)")
    tg.add_argument("action", choices=("setup", "check", "run"))
    sub.add_parser("runners", help="List scheduled jobs, their times and whether they can run")
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
        elif args.command == "ledger" and args.action == "import":
            result = ledger.import_inbox(root)
            print("Posted " + str(result["posted"]) + ", awaiting a rule " + str(result["review"])
                  + ", duplicates skipped " + str(result["skipped_dup"]) + ".")
            for error in result["errors"]:
                print("Not imported: " + error, file=sys.stderr)
            return 1 if result["errors"] else 0
        elif args.command == "ledger":
            from datetime import date
            print("Ledger saved: " + str(ledger.render(root, args.month or date.today().strftime("%Y-%m"))))
        elif args.command == "learn":
            print("Learning report saved: " + str(learning.report(root)))
        elif args.command == "maintain":
            print("Maintenance report saved: " + str(maintain.run(root)))
        elif args.command == "run":
            record = runners.run(root, args.runner, force=args.force)
            print(args.runner + ": " + record["status"] + (" — " + record["report"] if record.get("report") else "")
                  + (" (" + record["error"] + ")" if record.get("error") else ""))
            return 0 if record["status"] in ("ok", "skipped-done", "skipped-locked") else 1
        elif args.command == "schedule":
            if args.action in ("set", "off"):
                _, config = core.load(root)
                current = runners.setting(config, args.runner)
                if args.action == "set":
                    schedule.set_runner(root, args.runner, args.times, args.days or current["days"], True, args.assistant)
                else:
                    schedule.set_runner(root, args.runner, ",".join(current["times"]), current["days"], False)
                print("Saved. Apply with: life-kit --workspace " + str(root) + " schedule install")
            elif args.action == "install":
                for line in schedule.install(root, dry_run=args.dry_run):
                    print(line)
            elif args.action == "remove":
                for line in schedule.remove(root) or ["Nothing was installed."]:
                    print(line)
            else:
                print("\n".join(schedule.status(root)))
        elif args.command == "telegram":
            if args.action == "setup":
                telegram.setup(root, wizard.ConsoleIO())
                print("Install the background service: life-kit --workspace " + str(root) + " schedule install")
            elif args.action == "check":
                _, config = core.load(root)
                token = core.secret(root, "telegram_token")
                if not token:
                    raise ValueError("No bot token saved. Run: life-kit telegram setup")
                me = telegram.Api(token).call("getMe")
                owner = (config.get("telegram") or {}).get("owner")
                print("Bot @" + me.get("username", "?") + " reachable; " + ("paired with one private chat." if owner else "not paired."))
            else:
                telegram.run(root)
        elif args.command == "runners":
            root, config = core.load(root)
            ready = runners.available(config)
            for rid, r in runners.RUNNERS.items():
                s = runners.setting(config, rid)
                print(rid + ": " + r["title"] + " — " + ",".join(s["times"]) + " " + s["days"] + "; "
                      + ("installed" if s["enabled"] else "not scheduled") + ("" if rid in ready else "; needs area " + "/".join(r["domains_any"] or ["-"])
                         + (" and connection " + "/".join(r["needs_any"]) if r["needs_any"] else "")))
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
            records = connections.status(root)
            for conn_id in connections.enabled(root):
                r = records.get(conn_id, {})
                print(conn_id + ": " + ("verified read " + r["last_read_at"] if r.get("status") == "ok"
                                        else "configured, not verified" + (" (" + r["status"] + ")" if r.get("status") else "")))
            print("Scheduled jobs: " + schedule.status(root)[-1].replace("Installed with the system scheduler", "installed").replace("Not installed. Run: life-kit schedule install", "not installed"))
            print("Provider authentication/network access: only as shown above; doctor makes no network calls.")
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
    except (ValueError, OSError, UnicodeError, telegram.TelegramError) as exc:
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
