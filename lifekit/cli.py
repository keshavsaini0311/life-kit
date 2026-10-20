"""Command-line interface; all writes stay in the explicitly selected workspace."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from . import core


def main(argv=None):
    parser = argparse.ArgumentParser(description="Life Kit: a local workspace for your own routines.")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"), help="Private data folder (default: ./workspace)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a new private workspace with blank context")
    init.add_argument("--currency", default="INR")
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
    except (ValueError, OSError, UnicodeError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1
