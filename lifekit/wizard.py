"""Resumable, explained setup. Answers save after every question to .local/setup-answers.json."""
import getpass
import json
from pathlib import Path
import subprocess
import sys

from . import catalog, connections, core, questions, render, runners, schedule, telegram

ANSWERS = ".local/setup-answers.json"
BACK = object()


class ConsoleIO:
    def ask(self, text, secret=False):
        return getpass.getpass(text) if secret else input(text)

    def say(self, text):
        print(text)


def load_answers(root):
    path = Path(root) / ANSWERS
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_answers(root, answers):
    core.private_write(Path(root) / ANSWERS, core.json_text(answers))


def _find(question_id):
    for q in questions.QUESTIONS:
        if q["id"] == question_id:
            return q
    raise ValueError("Unknown setup answer: " + question_id)


def _store(root, q, value):
    """Parse and store one answer; secrets go to the secret store, never into answers."""
    if value is None:
        return None
    if q["kind"] == "secret":
        core.save_secret(root, q["secret_name"], str(value).strip())
        return "<stored>"
    return questions.parse(q, value)


def _ask_one(root, io, q, answers):
    io.say("")
    io.say("? " + q["prompt"])
    io.say("  Why: " + q["why"])
    io.say("  Example: " + q["example"])
    io.say("  If you skip: " + q["skip"])
    if q.get("choices"):
        io.say("  Choices: " + ", ".join(str(i) + ") " + c for i, c in enumerate(q["choices"], 1)))
    default = q["default"](answers) if q.get("default") else None
    if default:
        io.say("  Press Enter for: " + default)
    while True:
        raw = io.ask("> ", secret=q["kind"] == "secret")
        word = raw.strip().lower()
        if word == "back":
            return BACK
        if word == "skip":
            if q["kind"] == "currency":
                io.say("  This one is required.")
                continue
            return None
        if not raw.strip() and default:
            raw = default
        try:
            return _store(root, q, raw)
        except ValueError as exc:
            io.say("  " + str(exc))


def run(root, io=None, answers=None, answers_file=None, interactive=True, only=None):
    """Ask what is still unanswered, then apply. `only` limits question ids (tests, partial re-runs)."""
    root = Path(root).expanduser().resolve()
    io = io or ConsoleIO()
    given = dict(json.loads(Path(answers_file).read_text(encoding="utf-8"))) if answers_file else {}
    given.update(answers or {})
    initialized = (root / "life.json").is_file()
    stored = load_answers(root) if initialized else {}
    if initialized:
        _, config = core.load(root)
        if config["schema_version"] != core.CONFIG_SCHEMA:
            io.say("Upgraded workspace config; backup at " + str(core.migrate(root)))
        stored.setdefault("basics.currency", config["currency"])
    for key, value in given.items():
        stored[key] = _store(root, _find(key), value) if initialized or _find(key)["kind"] != "secret" else value
    if not initialized:
        if "basics.currency" not in stored:
            if not interactive:
                raise ValueError("basics.currency is required.")
            io.say("== Basics ==\n" + questions.SECTIONS[0][2])
            value = _ask_one(root, io, _find("basics.currency"), stored)
            stored["basics.currency"] = value if value is not BACK else None
        if not stored.get("basics.currency"):
            raise ValueError("basics.currency is required.")
        core.init(root, stored["basics.currency"])
        for key, value in list(stored.items()):  # secrets given before init can be stored now
            if _find(key)["kind"] == "secret" and value not in (None, "<stored>"):
                stored[key] = _store(root, _find(key), value)
    save_answers(root, stored)

    history, section = [], "basics" if not initialized else None
    while interactive:
        todo = [q for q in questions.QUESTIONS if (only is None or q["id"] in only)
                and q["id"] not in stored and questions.applies(q, stored)]
        if not todo:
            break
        q = todo[0]
        if q["section"] != section:
            section = q["section"]
            _, title, intro = next(s for s in questions.SECTIONS if s[0] == section)
            io.say("\n== " + title + " ==\n" + intro)
        value = _ask_one(root, io, q, stored)
        if value is BACK:
            if history:
                stored.pop(history.pop())
                save_answers(root, stored)
            continue
        stored[q["id"]] = value
        history.append(q["id"])
        save_answers(root, stored)
    for rel in finish(root, stored):
        if rel.endswith(".suggested"):
            io.say("Kept your edited " + rel[:-10] + "; new version saved as " + rel)
    integrate(root, stored, io, interactive=interactive)
    return stored


def integrate(root, answers, io, run=subprocess.run, interactive=True):
    """Plugins and connection checks: the only setup steps that start other programs, each opted into."""
    plugins = [p for p in catalog.PLUGINS if p["id"] in (answers.get("plugins.selected") or [])]
    for plugin in plugins:
        if answers.get("plugins.install_now"):
            try:
                result = run(plugin["install"].split(), capture_output=True, text=True, timeout=300)
                io.say(("Installed " if result.returncode == 0 else "Could not install ") + plugin["id"]
                       + ("" if result.returncode == 0 else "; run: " + plugin["install"]))
            except (OSError, subprocess.TimeoutExpired):
                io.say("Could not run Claude Code; install later with: " + plugin["install"])
        else:
            io.say("Install later: " + plugin["install"])
    for conn_id in answers.get("connections.selected") or []:
        item = connections.entry(root, conn_id)
        io.say("\n" + item["title"] + " — how to log in:")
        for step in item["login"]:
            io.say("  - " + step)
        if answers.get("connections.verify_now") and item.get("verify"):
            try:
                record = connections.verify(root, conn_id, run=run)
                io.say("  Check: " + record["status"] + ("" if record["status"] == "ok" else " (" + str(record.get("error")) + ")"))
            except ValueError as exc:
                io.say("  Check skipped: " + str(exc))
    if answers.get("telegram.enabled") and not (core.load(root)[1].get("telegram") or {}).get("owner"):
        if interactive:
            io.say("\n== Pair your Telegram bot ==")
            try:
                telegram.setup(root, io)
            except (ValueError, telegram.TelegramError) as exc:
                io.say("Telegram not paired: " + str(exc) + " Try again with: life-kit telegram setup")
        else:
            io.say("Pair Telegram later with: life-kit --workspace " + str(root) + " telegram setup")
    if answers.get("runners.install_now"):
        try:
            for line in schedule.install(root, run=run):
                io.say("  " + line)
            io.say("Scheduled jobs installed. Change a time later: life-kit schedule set ID HH:MM [days]")
        except ValueError as exc:
            io.say("Could not install schedules: " + str(exc))
        if sys.platform == "darwin" and any(part in ("Desktop", "Documents", "Downloads") for part in Path(root).parts):
            io.say("macOS note: background jobs may be blocked from reading ~/" + next(p for p in Path(root).parts if p in
                   ("Desktop", "Documents", "Downloads")) + ". If a log says 'Operation not permitted', allow Python in "
                   "System Settings → Privacy & Security → Files and Folders (or Full Disk Access), or keep the "
                   "workspace in your home folder instead.")


def finish(root, answers):
    """Save life.json settings, then render context files and skills. Returns paths written."""
    def change(config):
        profile = config.setdefault("profile", {})
        for key in ("name", "timezone"):
            if "basics." + key in answers:
                profile[key] = answers["basics." + key]
        if "domains.enabled" in answers:
            config["domains"] = answers["domains.enabled"] or []
        if "telegram.enabled" in answers:
            tg = config.setdefault("telegram", {})
            tg["enabled"] = bool(answers["telegram.enabled"])
            for key in ("reply_domains", "notify"):
                if "telegram." + key in answers:
                    tg[key] = answers["telegram." + key] or []
        if "assistants.enabled" in answers:
            enabled = answers["assistants.enabled"] or []
            config["assistants"] = enabled
            config["primary_assistant"] = answers.get("assistants.primary") or (enabled[0] if enabled else None)
    core.update_config(root, change)
    written = render.apply(root, answers)
    if answers.get("connections.selected"):
        written += connections.write_configs(root, answers["connections.selected"])
    if "runners.selected" in answers:
        picked = answers["runners.selected"] or []
        for rid in runners.RUNNERS:
            plan = answers.get("runner." + rid) or {"times": runners.RUNNERS[rid]["times"], "days": runners.RUNNERS[rid]["days"]}
            schedule.set_runner(root, rid, ",".join(plan["times"]), plan["days"], enabled=rid in picked)
    return written
