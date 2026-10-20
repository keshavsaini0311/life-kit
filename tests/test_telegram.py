import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from lifekit import core, telegram

OWNER = {"chat_id": 42, "user_id": 7}
NOW = 1_800_000_000


def msg(text, chat_id=42, user_id=7, chat_type="private", age=0):
    return {"message_id": 1, "date": NOW - age, "text": text,
            "chat": {"id": chat_id, "type": chat_type}, "from": {"id": user_id}}


class Quiet:
    def ask(self, text, secret=False):
        raise AssertionError(text)

    def say(self, text):
        pass


class FakeApi:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def call(self, method, **params):
        self.calls.append((method, params))
        value = self.responses.get(method, {})
        return value.pop(0) if isinstance(value, list) else value


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = core.init(Path(self.temp.name) / "w", "USD")
        core.update_config(self.root, lambda c: c.update(
            domains=["career", "finance"], telegram={"enabled": True, "owner": OWNER, "reply_domains": ["career"]}))

    def config(self):
        return core.load(self.root)[1]

    def handle(self, text, **kw):
        return telegram.handle(self.root, self.config(), msg(text, **kw), NOW)

    def test_non_owner_ignored(self):
        self.assertIsNone(self.handle("/status", chat_id=99))
        self.assertIsNone(self.handle("/status", user_id=99))
        self.assertIsNone(self.handle("/status", chat_type="group"))
        self.assertIsNotNone(self.handle("/status"))

    def test_stale_command_expires(self):
        reply = self.handle("/checkin sleep=7", age=31 * 60)
        self.assertIn("expired", reply.lower())
        self.assertEqual(core.events(self.root), [])

    def test_checkin_command_writes_event(self):
        reply = self.handle("/checkin sleep=7 gym=yes prep=30")
        self.assertIn("saved", reply.lower())
        values = core.events(self.root)[0]["values"]
        self.assertEqual(values, {"sleep_hours": 7.0, "gym": "yes", "prep_minutes": 30})

    def test_spend_command(self):
        self.handle("/spend 120.50 food lunch out")
        event = core.events(self.root)[0]
        self.assertEqual((event["amount"], event["category"], event["note"]), ("120.50", "food", "lunch out"))

    def test_bad_command_input_is_explained(self):
        self.assertIn("sleep=", self.handle("/checkin sleep=lots"))
        self.assertEqual(core.events(self.root), [])

    def test_runner_command_queues_task(self):
        reply = self.handle("/job_discovery")
        self.assertIn("queued", reply.lower())
        task = telegram.Queue(self.root).next()
        self.assertEqual((task["kind"], task["arg"]), ("run", "job-discovery"))

    def test_cancel_queued(self):
        self.handle("/report")
        task = telegram.Queue(self.root).recent(1)[0]
        self.assertIn("cancel", self.handle("/cancel " + str(task["id"])).lower())
        self.assertIsNone(telegram.Queue(self.root).next())

    def test_finance_reply_is_status_only(self):
        text = telegram.reply_text(self.config(), ["finance"], "Balance 5000", "finance-capture: ok")
        self.assertNotIn("5000", text)
        self.assertIn("saved on your computer", text)

    def test_career_reply_has_content(self):
        text = telegram.reply_text(self.config(), ["career"], "Role at Example Co", "job-discovery: ok")
        self.assertIn("Role at Example Co", text)

    def test_mixed_domains_status_only(self):
        text = telegram.reply_text(self.config(), ["career", "personal"], "secret stuff", "nightly-report: ok")
        self.assertNotIn("secret stuff", text)

    def test_pairing_code_expires_after_5_min(self):
        pending = {"code": "abc123", "expires": NOW + 300}
        late = [{"update_id": 1, "message": msg("/pair abc123", chat_id=5, user_id=6)}]
        self.assertIsNone(telegram.pair_from_updates(self.root, late, pending, NOW + 301))
        owner = telegram.pair_from_updates(self.root, late, pending, NOW + 10)
        self.assertEqual(owner, {"chat_id": 5, "user_id": 6})
        self.assertEqual(self.config()["telegram"]["owner"], {"chat_id": 5, "user_id": 6})

    def test_pairing_rejects_groups_and_wrong_code(self):
        pending = {"code": "abc123", "expires": NOW + 300}
        updates = [{"update_id": 1, "message": msg("/pair abc123", chat_type="group")},
                   {"update_id": 2, "message": msg("/pair wrong")}]
        self.assertIsNone(telegram.pair_from_updates(self.root, updates, pending, NOW))

    def test_refuses_existing_webhook(self):
        api = FakeApi({"getMe": {"username": "my_life_bot"}, "getWebhookInfo": {"url": "https://other.example.com/hook"}})
        with self.assertRaises(ValueError):
            telegram.start_pairing(self.root, api, now=NOW)

    def test_token_not_logged(self):
        token = "123456:" + "A" * 35

        def opener(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"ok":false}'))
        api = telegram.Api(token, opener=opener)
        with self.assertRaises(telegram.TelegramError) as ctx:
            api.call("getMe")
        self.assertNotIn(token, str(ctx.exception))
        self.assertNotIn(token, repr(ctx.exception))
        self.assertEqual(ctx.exception.category, "auth")

    def test_notifications_for_finished_runs_once(self):
        status = {"job-discovery": {"last": {"status": "ok", "finished_at": "2026-10-20T08:05:00+00:00",
                                             "report": str(self.root / "r.md")}}}
        (self.root / "r.md").write_text("Three roles found")
        (self.root / ".local/runners").mkdir(parents=True, exist_ok=True)
        (self.root / ".local/runners/status.json").write_text(json.dumps(status))
        first = telegram.pending_notifications(self.root, self.config())
        self.assertEqual(len(first), 1)
        self.assertIn("Three roles found", first[0])
        self.assertEqual(telegram.pending_notifications(self.root, self.config()), [])

    def test_worker_runs_task_and_replies_status_only(self):
        queue = telegram.Queue(self.root)
        queue.add("run", "maintain")
        api = FakeApi()
        rounds = iter([False, True])
        telegram.work(self.root, api, stop=lambda: next(rounds))
        sent = [p["text"] for m, p in api.calls if m == "sendMessage"]
        self.assertEqual(len(sent), 1)
        self.assertIn("maintain: ok", sent[0])
        self.assertNotIn("Going stale", sent[0])  # maintenance covers every area, so content stays local
        self.assertEqual(queue.recent(1)[0]["state"], "ok")

    def test_wizard_saves_telegram_choices(self):
        from lifekit import wizard
        root = Path(self.temp.name) / "fresh"
        wizard.run(root, io=Quiet(), interactive=False, answers={"basics.currency": "USD", "telegram.enabled": True,
                                                     "telegram.reply_domains": ["career", "work"]})
        tg = core.load(root)[1]["telegram"]
        self.assertEqual((tg["enabled"], tg["reply_domains"]), (True, ["career", "work"]))
        self.assertNotIn("owner", tg)

    def test_stale_queued_task_expires_instead_of_running(self):
        queue = telegram.Queue(self.root)
        task = queue.add("run", "maintain")
        queue.db.execute("UPDATE tasks SET created = ? WHERE id = ?", (0, task))
        queue.db.commit()
        api = FakeApi()
        rounds = iter([False, True])
        telegram.work(self.root, api, stop=lambda: next(rounds))
        self.assertEqual(queue.recent(1)[0]["state"], "expired")
        self.assertIn("expired", api.calls[0][1]["text"])

    def test_running_tasks_reset_on_startup(self):
        queue = telegram.Queue(self.root)
        task = queue.add("run", "maintain")
        queue.set_state(task, "running")
        telegram.recover(queue)
        self.assertEqual(queue.recent(1)[0]["state"], "failed")

    def test_worker_survives_unexpected_error(self):
        from unittest import mock
        queue = telegram.Queue(self.root)
        queue.add("run", "maintain")
        rounds = iter([False, True])
        with mock.patch.object(telegram.runners, "run", side_effect=KeyError("boom")):
            telegram.work(self.root, FakeApi(), stop=lambda: next(rounds))
        self.assertEqual(queue.recent(1)[0]["state"], "failed")

    def test_notification_kept_when_send_fails(self):
        status = {"learn": {"last": {"status": "ok", "finished_at": "2026-10-20T19:05:00+00:00"}}}
        (self.root / ".local/runners").mkdir(parents=True, exist_ok=True)
        (self.root / ".local/runners/status.json").write_text(json.dumps(status))
        def failing(text):
            raise telegram.TelegramError("network")
        telegram.send_notifications(self.root, self.config(), failing)
        sent = []
        telegram.send_notifications(self.root, self.config(), sent.append)
        self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
