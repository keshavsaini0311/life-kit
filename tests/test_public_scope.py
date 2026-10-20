"""Public setup offers general routines; removed workflows cannot be generated or invoked."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lifekit import catalog, connections, core, questions, render, runners, wizard


class Quiet:
    def say(self, text):
        pass


class PublicScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = core.init(Path(self.temp.name) / "workspace", "USD")

    def test_fresh_setup_has_no_removed_resources(self):
        source = Path(__file__).resolve().parents[1]
        wizard.run(self.root, io=Quiet(), interactive=False, answers_file=source / "examples/answers.json")
        removed = {"job-hunt", "hiring-outreach", "find-contact", "apply-autofill", "prep"}
        names = {p.name for p in (self.root / ".agents/skills").iterdir()}
        self.assertFalse(names & removed)
        self.assertIn("study", names)
        self.assertFalse((self.root / "career").exists())
        text = (self.root / "LIFE.md").read_text()
        for phrase in ("job search", "outreach", "recruiter", "resume"):
            self.assertNotIn(phrase, text.lower())

    def test_removed_connection_and_runner_not_offered_or_callable(self):
        self.assertNotIn("linkedin", {c["id"] for c in catalog.CONNECTIONS})
        self.assertNotIn("job-discovery", runners.RUNNERS)
        with self.assertRaisesRegex(ValueError, "Unknown runner"):
            runners.run(self.root, "job-discovery")
        with self.assertRaisesRegex(ValueError, "Unknown connection"):
            connections.entry(self.root, "linkedin")
        ids = {q["id"] for q in questions.QUESTIONS}
        self.assertFalse(any(q.startswith("career.") for q in ids))
        self.assertIn("learning.goals", ids)
        self.assertIn("learning.topics", ids)

    def test_retired_config_is_not_activated_and_user_files_survive(self):
        core.update_config(self.root, lambda c: c.update(connections={"linkedin": {}}, domains=["career"]))
        own = self.root / "career/context.md"
        own.parent.mkdir()
        own.write_text("My existing private notes")
        render.apply(self.root, {"domains.enabled": ["career"]})
        self.assertEqual(own.read_text(), "My existing private notes")
        self.assertEqual(connections.enabled(self.root), [])
        self.assertNotIn("job-discovery", runners.available(core.load(self.root)[1]))

    def test_historical_events_readable_but_not_new_cli_choices(self):
        at = datetime.now(timezone.utc).isoformat()
        base = dict(schema_version=core.EVENT_SCHEMA, source="user-reported", at=at, domain=core.LEGACY_DOMAINS[0])
        rows = [dict(base, id="old-activity", kind="action", channel="legacy", target="legacy", variant="unrecorded"),
                dict(base, id="old-outcome", kind="outcome", action_id="old-activity", stage=core.LEGACY_STAGES[0], evidence="legacy")]
        path = self.root / "learning/events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        before = path.read_bytes()
        self.assertEqual(len(core.events(self.root)), 2)
        self.assertEqual(core.snapshot(self.root)["actions"], 1)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            core.action(self.root, core.LEGACY_DOMAINS[0], "legacy", "legacy")
        with self.assertRaises(ValueError):
            core.outcome(self.root, "old-activity", core.LEGACY_STAGES[0], "new")

    def test_cli_supports_study_capture_and_no_resume_upload_option(self):
        command = [sys.executable, "-m", "lifekit", "--workspace", str(self.root)]
        result = subprocess.run(command + ["checkin", "--study", "25"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(core.snapshot(self.root)["self_reported_prep_minutes"], 25)
        result = subprocess.run(command + ["action", "--channel", "practice", "--target", "SQL", "--resume", "unused"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len(core.events(self.root)), 1)


if __name__ == "__main__":
    unittest.main()
