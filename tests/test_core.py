from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lifekit import core


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = core.init(Path(self.temp.name) / "private", "USD")

    def test_setup_is_blank_and_refuses_overwrite(self):
        before = (self.root / "personal/rules.md").read_bytes()
        self.assertEqual(core.events(self.root), [])
        with self.assertRaises(ValueError):
            core.init(self.root)
        self.assertEqual(before, (self.root / "personal/rules.md").read_bytes())

    def test_uninitialized_workspace_fails(self):
        with self.assertRaises(ValueError):
            core.snapshot(Path(self.temp.name) / "absent")

    def test_unknown_is_not_zero(self):
        status = core.snapshot(self.root)
        self.assertEqual(status["recorded_spend"], {})
        body = core.report(self.root).read_text()
        self.assertIn("unknown (no spend records)", body)
        self.assertIn("unknown, not proof of failure", body)

    def test_partial_checkin_does_not_invent_fields(self):
        event = core.checkin(self.root, gym="rest")
        self.assertEqual(event["values"], {"gym": "rest"})
        self.assertEqual(event["source"], "user-reported")

    def test_invalid_observations_never_write(self):
        for kwargs in ({"sleep": float("nan")}, {"sleep": -1}, {"sleep": 25}, {"prep": -1}, {"prep": 1.5}, {"gym": "maybe"}, {}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                core.checkin(self.root, **kwargs)
        for amount in ("nan", "inf", "-1", "0", "1.001", "bad"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                core.spend(self.root, amount, "food")
        self.assertEqual(core.events(self.root), [])

    def test_exact_money_and_currency(self):
        for _ in range(3):
            core.spend(self.root, "0.10", "food")
        self.assertEqual(core.snapshot(self.root)["recorded_spend"], {"USD": "0.30"})

    def test_retry_idempotency_and_conflict(self):
        first = core.checkin(self.root, prep=30, request_id="retry-1")
        again = core.checkin(self.root, prep=30, request_id="retry-1")
        self.assertEqual(first["id"], again["id"])
        with self.assertRaises(ValueError):
            core.checkin(self.root, prep=40, request_id="retry-1")
        self.assertEqual(len(core.events(self.root)), 1)

    def test_outcome_credits_only_specific_action(self):
        first = core.action(self.root, "career", "email", "same-person")
        core.action(self.root, "career", "email", "same-person")
        for _ in range(2):
            core.outcome(self.root, first["id"], "reply", "explicit self-report")
        core.outcome(self.root, first["id"], "receipt", "mail receipt")
        status = core.snapshot(self.root)
        self.assertEqual(status["actions"], 2)
        self.assertEqual(status["outcomes_by_action"]["reply"], 1)
        self.assertEqual(status["outcomes_by_action"]["receipt"], 1)
        self.assertEqual(status["outcomes_by_action"]["interview"], 0)

    def test_unlinked_outcome_is_rejected(self):
        with self.assertRaises(ValueError):
            core.outcome(self.root, "absent", "reply", "self-report")
        self.assertEqual(core.events(self.root), [])

    def test_outcome_keeps_action_domain(self):
        action = core.action(self.root, "work", "meeting", "fictional-review")
        outcome = core.outcome(self.root, action["id"], "reply", "self-report", request_id="work-reply")
        self.assertEqual(outcome["domain"], "work")
        self.assertEqual(core.outcome(self.root, action["id"], "reply", "self-report", request_id="work-reply")["id"], outcome["id"])

    def test_valid_log_without_final_newline_can_append(self):
        core.checkin(self.root, prep=20)
        path = self.root / "learning/events.jsonl"
        path.write_text(path.read_text().rstrip())
        core.checkin(self.root, prep=30)
        self.assertEqual(len(core.events(self.root)), 2)

    def test_outcome_cannot_reference_non_action(self):
        event = core.checkin(self.root, prep=30)
        with self.assertRaises(ValueError):
            core.outcome(self.root, event["id"], "reply", "self-report")

    def test_resume_fingerprint_no_file_copy(self):
        resume = Path(self.temp.name) / "resume.txt"
        resume.write_text("fictional resume")
        first = core.action(self.root, "career", "application", "fictional-role", resume=resume)
        resume.write_text("fictional revision")
        second = core.action(self.root, "career", "application", "fictional-role", resume=resume)
        self.assertNotEqual(first["resume_sha256"], second["resume_sha256"])
        self.assertNotIn("fictional revision", (self.root / "learning/events.jsonl").read_text())

    def test_future_event_excluded(self):
        core.checkin(self.root, prep=30)
        path = self.root / "learning/events.jsonl"
        row = json.loads(path.read_text())
        row["at"] = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        path.write_text(json.dumps(row) + "\n")
        self.assertEqual(core.snapshot(self.root)["checkins"], 0)
        self.assertEqual(core.snapshot(self.root)["excluded_future_events"], 1)

    def test_corruption_is_reported_without_rewriting(self):
        core.checkin(self.root, prep=30)
        path = self.root / "learning/events.jsonl"
        path.write_text(path.read_text() + "{broken\n")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "line 2"):
            core.checkin(self.root, prep=40)
        self.assertEqual(before, path.read_bytes())

    def test_incomplete_event_rejected(self):
        row = core.checkin(self.root, prep=30)
        del row["values"]
        (self.root / "learning/events.jsonl").write_text(json.dumps(row) + "\n")
        with self.assertRaisesRegex(ValueError, "line 1"):
            core.snapshot(self.root)

    def test_unsupported_schema_rejected(self):
        path = self.root / "life.json"
        config = json.loads(path.read_text())
        config["schema_version"] = 999
        path.write_text(json.dumps(config))
        with self.assertRaises(ValueError):
            core.checkin(self.root, prep=30)

    def test_concurrent_writes_preserve_all_events(self):
        def write(index):
            return core.spend(self.root, "1.10", "food", request_id="request-" + str(index))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(12)))
        self.assertEqual(len(core.events(self.root)), 12)
        self.assertEqual(core.snapshot(self.root)["recorded_spend"], {"USD": "13.20"})

    @unittest.skipIf(os.name == "nt", "Windows uses account ACLs")
    def test_private_posix_permissions(self):
        core.checkin(self.root, prep=30)
        self.assertEqual((self.root / "learning/events.jsonl").stat().st_mode & 0o777, 0o600)
        self.assertEqual(core.report(self.root).stat().st_mode & 0o777, 0o600)

    def test_cli_and_workspace_with_spaces(self):
        root = Path(self.temp.name) / "with spaces"
        base = [sys.executable, "-m", "lifekit", "--workspace", str(root)]
        for tail in (["init"], ["checkin", "--prep", "20"], ["doctor"], ["report"]):
            result = subprocess.run(base + tail, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(base + ["status"], capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["self_reported_prep_minutes"], 20)
        result = subprocess.run(base + ["spend", "NaN", "--category", "food"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
