"""Scheduled jobs: one instance at a time, once per scheduled slot, bounded, read-only, reports stay local."""
from contextlib import contextmanager
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
from string import Template
import subprocess
import tempfile

from . import connections, core, maintain

TEMPLATES = Path(__file__).resolve().parent / "templates/runners"
WORK = ["github", "clickup", "slack", "linear", "notion", "signoz"]
# kind: local (no assistant) | agent. needs_any: at least one enabled connection, [] = none needed.
RUNNERS = {
    "maintain": dict(title="Import statements, rebuild ledgers and learning, list stale data", kind="local",
                     times=["21:45"], days="daily", domains_any=[], needs_any=[]),
    "nightly-report": dict(title="Nightly review and next actions", kind="agent", times=["22:00"], days="daily",
                           domains_any=[], needs_any=[]),
    "work-brief": dict(title="Morning work brief (tasks, PRs, mentions, service health)", kind="agent",
                       times=["08:30"], days="weekdays", domains_any=["work"], needs_any=WORK),
    "inbox-review": dict(title="Inbox follow-up review", kind="agent", times=["09:00", "19:00"], days="daily",
                         domains_any=["work", "personal"], needs_any=["gmail"]),
    "calendar-prep": dict(title="Calendar-aware study suggestions", kind="agent", times=["21:30"], days="daily",
                          domains_any=["learning", "personal"], needs_any=["google-calendar"]),
    "finance-capture": dict(title="Weekly money check (ledger, review rows, broker holdings)", kind="agent",
                            times=["18:00"], days="sun", domains_any=["finance"], needs_any=[]),
    "receipt-review": dict(title="Receipt emails to confirm as spending", kind="agent", times=["21:00"], days="daily",
                           domains_any=["finance"], needs_any=["gmail"]),
    "learn": dict(title="Weekly review of learning and activity outcomes", kind="agent", times=["19:00"], days="sun",
                  domains_any=[], needs_any=[]),
}
OPTIONAL_READS = {"finance-capture": ["kite"], "nightly-report": []}
DAYS = ("daily", "weekdays", "mon", "tue", "wed", "thu", "fri", "sat", "sun")
STATE = ".local/runners"


def setting(config, runner_id):
    """Effective times/days/assistant: defaults overridden by life.json runners.<id>."""
    base = RUNNERS[runner_id]
    custom = (config.get("runners") or {}).get(runner_id, {})
    return {"enabled": custom.get("enabled", False), "times": custom.get("times") or base["times"],
            "days": custom.get("days") or base["days"], "assistant": custom.get("assistant")}


def _uses(config, runner_id):
    """Enabled connections this runner may read."""
    enabled = list((config.get("connections") or {}).keys())
    base = RUNNERS[runner_id]
    return [c for c in base["needs_any"] + OPTIONAL_READS.get(runner_id, []) if c in enabled]


def available(config):
    domains = config.get("domains") or []
    enabled = list((config.get("connections") or {}).keys())
    return [rid for rid, r in RUNNERS.items()
            if (not r["domains_any"] or set(r["domains_any"]) & set(domains))
            and (not r["needs_any"] or set(r["needs_any"]) & set(enabled))]


def _codex_servers(root):
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    names = set()
    for path in (home / "config.toml", Path(root) / ".codex/config.toml"):
        if path.is_file():
            names.update(m.group(2) for m in re.finditer(r'^\s*\[mcp_servers\.("?)([^\]"]+)\1\]', path.read_text(encoding="utf-8"), re.M))
    return names


def command(root, config, runner_id):
    """(argv, assistant) for an agent runner. The prompt goes on stdin."""
    items = [connections.entry(root, c) for c in _uses(config, runner_id)]
    enabled_assistants = config.get("assistants") or ["claude"]
    preferred = [setting(config, runner_id)["assistant"], config.get("primary_assistant")] + enabled_assistants
    able = [a for a in preferred if a and a in enabled_assistants and all(a in i["headless"] for i in items)]
    if not able:
        raise ValueError(runner_id + " needs an assistant that can read " + ", ".join(i["title"] for i in items))
    return agent_argv(root, able[0], items, RUNNERS[runner_id].get("web", False)), able[0]


def claude_lockdown(builtins, mcp_tools):
    """Only these tools exist or are allowed; anything else is denied without asking, whatever the
    user's own permission mode. --allowedTools alone would only pre-approve, not restrict."""
    return ["--permission-mode", "dontAsk", "--tools", ",".join(builtins),
            "--allowedTools", ",".join(builtins + list(mcp_tools)),
            "--disallowedTools", "Bash,Edit,Write,NotebookEdit"]


def resolve(argv):
    """Full path for the assistant CLI (finds Windows .cmd shims that Popen would miss)."""
    found = shutil.which(argv[0])
    return [found] + list(argv[1:]) if found else list(argv)


def agent_argv(root, assistant, items=(), web=False):
    """Read-only assistant command limited to the read tools of `items`. The prompt goes on stdin."""
    if assistant == "claude":
        builtins = ["Read", "Glob", "Grep"] + (["WebSearch", "WebFetch"] if web else [])
        mcp = [connections.tool_name(i, t) for i in items for t in i["read_tools"]]
        argv = ["claude", "-p", "--output-format", "text", "--max-turns", "40"] + claude_lockdown(builtins, mcp)
        if any(connections.claude_server(i) for i in items):
            argv += ["--mcp-config=" + str(Path(root) / ".mcp.json")]
        return argv
    argv = ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--cd", str(root), "--sandbox", "read-only",
            "-c", "features.apps=" + ("true" if any(i["server"]["type"] == "account" for i in items) else "false"),
            "-c", "features.plugins=false", "-c", "features.browser_use=false", "-c", "features.computer_use=false"]
    if web:
        argv += ["-c", 'web_search="live"']
    used = {i["id"] for i in items}
    for name in sorted(_codex_servers(root) - used):
        argv += ["-c", "mcp_servers." + name + ".enabled=false"]
    for item in items:
        argv += connections.codex_overrides(item)
    return argv


def ask(root, config, text, run=subprocess.run, timeout=600):
    """One read-only question to the primary assistant with no connections. Returns its answer."""
    assistant = config.get("primary_assistant") or (config.get("assistants") or ["claude"])[0]
    argv = agent_argv(root, assistant)
    out = None
    if assistant == "codex":
        fd, out = tempfile.mkstemp(prefix=".ask-", dir=str(Path(root) / ".local"))
        os.close(fd)
        argv += ["--output-last-message", out]
    try:
        result = run(resolve(argv), input=text, cwd=str(root), env=connections.env(root), capture_output=True, text=True, timeout=timeout)
        answer = (Path(out).read_text(encoding="utf-8") if out else "") or result.stdout
    except FileNotFoundError:
        raise ValueError(assistant + " is not installed")
    except subprocess.TimeoutExpired:
        raise ValueError("no answer within " + str(timeout) + "s")
    finally:
        if out and os.path.exists(out):
            os.unlink(out)
    if result.returncode != 0:
        raise ValueError(assistant + " exited with " + str(result.returncode))
    return answer.strip()


@contextmanager
def single_instance(root, runner_id):
    """Yields True if this process holds the runner's lock, False if another run holds it."""
    path = Path(root) / STATE / (runner_id + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+") as stream:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)


def slot(times, now):
    """The scheduled time this run belongs to: the latest one at or before now, else 'manual'."""
    past = [t for t in sorted(times) if t <= now.strftime("%H:%M")]
    return now.date().isoformat() + " " + (past[-1] if past else "manual")


def _status(root):
    path = Path(root) / STATE / "status.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save(root, runner_id, key, record):
    with core.locked(root):
        data = _status(root)
        entry = data.setdefault(runner_id, {"slots": {}})
        entry["slots"][key] = record["status"]
        entry["slots"] = dict(sorted(entry["slots"].items())[-30:])
        entry["last"] = record
        core.private_write(Path(root) / STATE / "status.json", core.json_text(data))
    return record


def _kill(process):
    try:
        if os.name != "nt" and process.pid:
            os.killpg(process.pid, signal.SIGKILL)  # the assistant and anything it started
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def prompt(root, config, runner_id, snapshot_text):
    common = (TEMPLATES / "_common.md").read_text(encoding="utf-8")
    task = (TEMPLATES / (runner_id + ".md")).read_text(encoding="utf-8")
    values = {"name": (config.get("profile") or {}).get("name") or "the user", "workspace": str(root),
              "today": date.today().isoformat(), "snapshot": snapshot_text}
    return Template(common + "\n" + task).substitute(values)


def run(root, runner_id, now=None, popen=subprocess.Popen, timeout=900, force=False):
    root, config = core.load(root)
    if runner_id not in RUNNERS:
        raise ValueError("Unknown runner: " + runner_id + ". Choose from " + ", ".join(RUNNERS))
    if runner_id not in available(config):
        raise ValueError(runner_id + " needs an enabled area (" + ", ".join(RUNNERS[runner_id]["domains_any"]) + ") or connection ("
                         + ", ".join(RUNNERS[runner_id]["needs_any"]) + ").")
    now = now or datetime.now()
    key = slot(setting(config, runner_id)["times"], now)
    if not force and _status(root).get(runner_id, {}).get("slots", {}).get(key) == "ok":
        return {"status": "skipped-done", "slot": key}
    with single_instance(root, runner_id) as acquired:
        if not acquired:
            return {"status": "skipped-locked", "slot": key}
        if not force and _status(root).get(runner_id, {}).get("slots", {}).get(key) == "ok":
            return {"status": "skipped-done", "slot": key}  # another run finished while we waited
        record = {"slot": key, "started_at": core.timestamp()}
        if RUNNERS[runner_id]["kind"] == "local":
            try:
                record["report"] = str(maintain.run(root, now.date()))
            except (ValueError, OSError) as exc:
                return _save(root, runner_id, key, dict(record, status="failed", error=str(exc)[:300]))
            return _save(root, runner_id, key, dict(record, status="ok", finished_at=core.timestamp()))
        snapshot = core.report(root, 7)  # saved first, so a failed agent still leaves a report
        record["snapshot"] = str(snapshot)
        try:
            argv, assistant = command(root, config, runner_id)
        except ValueError as exc:
            return _save(root, runner_id, key, dict(record, status="unavailable", error=str(exc)))
        record["assistant"] = assistant
        out = None
        if assistant == "codex":
            fd, out = tempfile.mkstemp(prefix=".runner-", dir=str(Path(root) / STATE))
            os.close(fd)
            argv = argv + ["--output-last-message", out]
        log = Path(root) / ".local/logs" / (now.date().isoformat() + "-" + runner_id + ".log")
        log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        text = prompt(root, config, runner_id, snapshot.read_text(encoding="utf-8")).encode("utf-8")
        try:
            with log.open("wb") as stream:
                try:
                    process = popen(resolve(argv), cwd=str(root), env=connections.env(root), stdin=subprocess.PIPE,
                                    stdout=stream, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
                except FileNotFoundError:
                    return _save(root, runner_id, key, dict(record, status="unavailable", error=assistant + " not installed"))
                try:
                    process.communicate(text, timeout=timeout)
                except subprocess.TimeoutExpired:
                    _kill(process)
                    return _save(root, runner_id, key, dict(record, status="timeout", error="over " + str(timeout) + "s"))
            body = Path(out).read_text(encoding="utf-8") if out and os.path.exists(out) else ""
            body = body.strip() or log.read_text(encoding="utf-8", errors="replace")  # codex wrote no final message
        finally:
            if out and os.path.exists(out):
                os.unlink(out)
        if process.returncode != 0:
            return _save(root, runner_id, key, dict(record, status="failed", error="exit " + str(process.returncode) + "; see " + str(log)))
        report = Path(root) / ".local/reports" / (now.date().isoformat() + "-" + runner_id + ".md")
        core.private_write(report, "# " + RUNNERS[runner_id]["title"] + "\n\n_" + now.strftime("%Y-%m-%d %H:%M")
                           + " via " + assistant + ". Local only._\n\n" + body.strip() + "\n")
        return _save(root, runner_id, key, dict(record, status="ok", report=str(report), finished_at=core.timestamp()))
