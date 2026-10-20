"""Owner-paired Telegram channel: long polling (no public port), local queue, privacy-scoped replies.

Only the paired owner's private chat is obeyed. Commands older than 30 minutes expire. Replies carry
content only for domains listed in telegram.reply_domains; everything else gets a status line.
"""
from datetime import datetime
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import core, runners

MAX_AGE = 30 * 60
PAIRING_SECONDS = 300
ALL_DOMAINS = ["personal", "finance", "career", "work"]
HELP = ("/status — recent tasks\n/report — run tonight's review now\n/checkin sleep=7 gym=yes prep=30\n"
        "/spend AMOUNT CATEGORY [note]\n/outcome ACTION_ID STAGE [evidence]\n/ask [career|work|personal|finance] question\n"
        "/cancel TASK_ID\n{runners}")


class TelegramError(Exception):
    """Carries a category only, never the URL (which contains the bot token)."""

    def __init__(self, category):
        super().__init__("Telegram request failed: " + category)
        self.category = category


class Api:
    def __init__(self, token, opener=urllib.request.urlopen):
        self._token, self._opener = token, opener

    def call(self, method, timeout=30, **params):
        data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v
                                       for k, v in params.items()}).encode()
        request = urllib.request.Request("https://api.telegram.org/bot" + self._token + "/" + method, data)
        try:
            with self._opener(request, timeout=timeout + 15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TelegramError({401: "auth", 404: "auth", 409: "conflict", 429: "rate-limited"}.get(exc.code, "http")) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise TelegramError("network") from None
        if not body.get("ok"):
            raise TelegramError("rejected")
        return body["result"]


class Queue:
    def __init__(self, root):
        path = Path(root) / ".local/telegram.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, kind TEXT, arg TEXT, "
                            "state TEXT, created REAL, finished REAL, result TEXT)")
            self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

    def _rows(self, sql, args=()):
        with self.lock:
            cursor = self.db.execute(sql, args)
            names = [c[0] for c in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    def add(self, kind, arg):
        with self.lock, self.db:
            return self.db.execute("INSERT INTO tasks (kind, arg, state, created) VALUES (?, ?, 'queued', ?)",
                                   (kind, arg, time.time())).lastrowid

    def next(self):
        rows = self._rows("SELECT * FROM tasks WHERE state = 'queued' ORDER BY id LIMIT 1")
        return rows[0] if rows else None

    def set_state(self, task_id, state, result=""):
        with self.lock, self.db:
            self.db.execute("UPDATE tasks SET state = ?, result = ?, finished = ? WHERE id = ?",
                            (state, result, time.time(), task_id))

    def cancel(self, task_id):
        with self.lock, self.db:
            return self.db.execute("UPDATE tasks SET state = 'cancelled' WHERE id = ? AND state = 'queued'",
                                   (task_id,)).rowcount

    def recent(self, n=5):
        return self._rows("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (n,))

    def setting(self, key, value=None):
        if value is None:
            rows = self._rows("SELECT value FROM settings WHERE key = ?", (key,))
            return rows[0]["value"] if rows else None
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, str(value)))


def command_name(runner_id):
    return "/" + runner_id.replace("-", "_")  # Telegram commands allow only letters, digits and _


def runner_domains(runner_id):
    return runners.RUNNERS[runner_id]["domains_any"] or ALL_DOMAINS


def reply_text(config, domains, content, status):
    allowed = set((config.get("telegram") or {}).get("reply_domains") or [])
    if content and domains and set(domains) <= allowed:
        return (status + "\n\n" + content.strip())[:3900]
    return status + ("\nFull result saved on your computer." if content else "")


def _is_owner(config, message):
    owner = (config.get("telegram") or {}).get("owner") or {}
    chat = message.get("chat") or {}
    return (chat.get("type") == "private" and owner and chat.get("id") == owner.get("chat_id")
            and (message.get("from") or {}).get("id") == owner.get("user_id"))


def handle(root, config, message, now=None):
    """Reply text for one owner message, or None to ignore it silently."""
    if not _is_owner(config, message):
        return None
    now = now or time.time()
    if now - message.get("date", 0) > MAX_AGE:
        return "That command expired (sent over 30 minutes ago). Send it again if you still want it."
    text = (message.get("text") or "").strip()
    word, _, rest = text.partition(" ")
    word = word.split("@")[0].lower()
    rest = rest.strip()
    queue = Queue(root)
    ready = runners.available(config)
    try:
        if word in ("/start", "/help"):
            return HELP.format(runners="\n".join(command_name(r) + " — " + runners.RUNNERS[r]["title"] for r in ready))
        if word == "/status":
            lines = [str(t["id"]) + " " + t["kind"] + " " + (t["arg"] or "")[:30] + ": " + t["state"] for t in queue.recent(5)]
            return "Online.\n" + ("\n".join(lines) or "No tasks yet.")
        if word == "/checkin":
            fields = dict(part.split("=", 1) for part in rest.split() if "=" in part)
            unknown = set(fields) - {"sleep", "gym", "prep"}
            if unknown or not fields:
                return "Use: /checkin sleep=7 gym=yes|no|rest prep=30 (any of them)."
            try:
                sleep = float(fields["sleep"]) if "sleep" in fields else None
                prep = int(fields["prep"]) if "prep" in fields else None
            except ValueError:
                return "Use numbers: /checkin sleep=7.5 prep=30"
            core.checkin(root, sleep, fields.get("gym"), prep, request_id="tg-" + str(message.get("message_id")) + "-" + str(message.get("date")))
            return "Check-in saved on your computer."
        if word == "/spend":
            parts = rest.split(None, 2)
            if len(parts) < 2:
                return "Use: /spend 120 food [note]"
            core.spend(root, parts[0], parts[1], parts[2] if len(parts) > 2 else "",
                       request_id="tg-" + str(message.get("message_id")) + "-" + str(message.get("date")))
            return "Spend saved on your computer."
        if word == "/outcome":
            parts = rest.split(None, 2)
            if len(parts) < 2:
                return "Use: /outcome ACTION_ID STAGE [evidence]. Stages: " + ", ".join(core.STAGES)
            evidence = "self-report via Telegram" + (": " + parts[2] if len(parts) > 2 else "")
            core.outcome(root, parts[0], parts[1], evidence)
            return "Outcome saved for " + parts[0] + "."
        if word == "/cancel":
            return ("Cancelled " + rest + ".") if rest.isdigit() and queue.cancel(int(rest)) else "Nothing queued with that ID."
        if word == "/report":
            return "Queued task " + str(queue.add("run", "nightly-report")) + ": nightly-report."
        if word == "/ask":
            if not rest:
                return "Use: /ask [career|work|personal|finance] your question"
            return "Queued task " + str(queue.add("ask", rest)) + "."
        for rid in ready:
            if word == command_name(rid):
                return "Queued task " + str(queue.add("run", rid)) + ": " + rid + "."
    except ValueError as exc:
        return "Not saved: " + str(exc)
    return "Unknown command. Send /help."


def start_pairing(root, api, now=None):
    """Check the bot, refuse a bot already used by another integration, return a 5-minute pairing code."""
    me = api.call("getMe")
    if (api.call("getWebhookInfo") or {}).get("url"):
        raise ValueError("This bot has a webhook set, so another integration uses it. Create a dedicated bot with @BotFather.")
    return {"code": secrets.token_hex(8), "expires": (now or time.time()) + PAIRING_SECONDS, "bot": me.get("username")}


def pair_from_updates(root, updates, pending, now=None):
    now = now or time.time()
    if now > pending["expires"]:
        return None
    for update in updates:
        message = update.get("message") or {}
        if (message.get("chat") or {}).get("type") == "private" and (message.get("text") or "").strip() == "/pair " + pending["code"]:
            owner = {"chat_id": message["chat"]["id"], "user_id": message["from"]["id"]}

            def change(config):
                tg = config.setdefault("telegram", {})
                tg.update(enabled=True, owner=owner)
                tg.setdefault("reply_domains", ["career"])
            core.update_config(root, change)
            return owner
    return None


def setup(root, io, api_factory=Api):
    io.say("1. In Telegram, open @BotFather (blue check), send /newbot and follow the steps.")
    io.say("2. Copy the token it gives you. Paste it below; it is hidden and stored only in this workspace.")
    token = io.ask("Bot token: ", secret=True).strip()
    if not token:
        raise ValueError("No token given; run `life-kit telegram setup` when ready.")
    api = api_factory(token)
    pending = start_pairing(root, api)
    core.save_secret(root, "telegram_token", token)
    io.say("3. From your own private chat with @" + str(pending["bot"]) + ", send exactly:\n\n   /pair " + pending["code"]
           + "\n\nWaiting up to 5 minutes...")
    offset = 0
    while time.time() < pending["expires"]:
        updates = api.call("getUpdates", timeout=20, offset=offset, allowed_updates=["message"])
        if updates:
            offset = updates[-1]["update_id"] + 1
        owner = pair_from_updates(root, updates, pending)
        if owner:
            Queue(root).setting("offset", offset)
            api.call("sendMessage", chat_id=owner["chat_id"], text="Paired with your Life Kit. Send /help.")
            io.say("Paired. Only that private chat can control this workspace.")
            return owner
    raise ValueError("Pairing code expired. Run `life-kit telegram setup` again.")


def pending_notifications(root, config):
    """One message per scheduled run finished since the last check, for runners in telegram.notify."""
    path = Path(root) / runners.STATE / "status.json"
    status = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    queue = Queue(root)
    seen = json.loads(queue.setting("notified") or "{}")
    wanted = (config.get("telegram") or {}).get("notify")
    messages = []
    for rid, entry in status.items():
        last = entry.get("last") or {}
        stamp = last.get("finished_at") or last.get("started_at")
        if rid not in runners.RUNNERS or not stamp or seen.get(rid) == stamp or (wanted is not None and rid not in wanted):
            continue
        content = ""
        if last.get("report") and Path(last["report"]).is_file():
            content = Path(last["report"]).read_text(encoding="utf-8")
        messages.append(reply_text(config, runner_domains(rid), content, rid + ": " + last.get("status", "unknown")))
        seen[rid] = stamp
    queue.setting("notified", json.dumps(seen))
    return messages


def _ask(root, config, text):
    scope, _, question = text.partition(" ")
    domains = [scope] if scope in ALL_DOMAINS else (config.get("domains") or ALL_DOMAINS)
    question = question if scope in ALL_DOMAINS else text
    path = Path(root) / ".local/reports" / ("ask-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".md")
    prompt = ("Answer " + ((config.get("profile") or {}).get("name") or "the user") + "'s question using only files in the " + ", ".join(domains) + " area(s) and personal/rules.md. "
              "Read-only: do not edit files or contact anyone. Question: " + question)
    output = runners.ask(root, config, prompt)
    core.private_write(path, output)
    return domains, output


def work(root, api, stop):
    """Worker thread: run queued tasks one at a time and reply within the privacy rule."""
    queue = Queue(root)
    while not stop():
        task = queue.next()
        if not task:
            time.sleep(2)
            continue
        queue.set_state(task["id"], "running")
        _, config = core.load(root)
        chat = config["telegram"]["owner"]["chat_id"]
        try:
            if task["kind"] == "run":
                record = runners.run(root, task["arg"], force=True)
                content = Path(record["report"]).read_text(encoding="utf-8") if record.get("report") else ""
                text = reply_text(config, runner_domains(task["arg"]), content, "Task " + str(task["id"]) + " " + task["arg"] + ": " + record["status"])
                state = record["status"]
            else:
                domains, output = _ask(root, config, task["arg"])
                text = reply_text(config, domains, output, "Task " + str(task["id"]) + " answered")
                state = "ok"
        except (ValueError, OSError) as exc:
            text, state = "Task " + str(task["id"]) + " failed: " + str(exc)[:200], "failed"
        queue.set_state(task["id"], state)
        try:
            api.call("sendMessage", chat_id=chat, text=text)
        except TelegramError:
            pass


def run(root, api=None, stop=lambda: False):
    """Foreground service: long-poll for owner commands, queue work, send notifications."""
    root, config = core.load(root)
    if not (config.get("telegram") or {}).get("owner"):
        raise ValueError("Telegram is not paired. Run `life-kit telegram setup`.")
    api = api or Api(core.secret(root, "telegram_token") or "")
    with runners.single_instance(root, "telegram") as acquired:
        if not acquired:
            raise ValueError("Another Telegram service is already running for this workspace.")
        queue = Queue(root)
        threading.Thread(target=work, args=(root, api, stop), daemon=True).start()
        offset = int(queue.setting("offset") or 0)
        while not stop():
            _, config = core.load(root)
            try:
                updates = api.call("getUpdates", timeout=50, offset=offset, allowed_updates=["message"])
            except TelegramError as exc:
                if exc.category == "auth":
                    raise ValueError("Telegram rejected the bot token. Run `life-kit telegram setup` again.")
                time.sleep(15)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                queue.setting("offset", offset)
                reply = handle(root, config, update.get("message") or {})
                if reply:
                    api.call("sendMessage", chat_id=config["telegram"]["owner"]["chat_id"], text=reply)
            for text in pending_notifications(root, config):
                api.call("sendMessage", chat_id=config["telegram"]["owner"]["chat_id"], text=text)
