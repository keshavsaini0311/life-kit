import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from lifekit import core, questions, wizard


class FakeIO:
    """Scripted answers; records everything shown and whether input was hidden."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.shown = []
        self.secret_prompts = []

    def ask(self, text, secret=False):
        self.shown.append(text)
        if secret:
            self.secret_prompts.append(text)
        if not self.replies:
            raise AssertionError("Unexpected question: " + text)
        return self.replies.pop(0)

    def say(self, text):
        self.shown.append(text)


def by_id(question_id):
    return next(q for q in questions.QUESTIONS if q["id"] == question_id)


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "life"

    def answers(self):
        return json.loads((self.root / ".local/setup-answers.json").read_text())

    def test_every_question_has_why_example_skip(self):
        ids = set()
        for q in questions.QUESTIONS:
            for key in ("id", "section", "prompt", "why", "example", "skip", "kind"):
                self.assertTrue(q.get(key), q.get("id", "?") + " lacks " + key)
            self.assertIn(q["section"], [s[0] for s in questions.SECTIONS])
            self.assertNotIn(q["id"], ids)
            ids.add(q["id"])

    def test_skip_records_none(self):
        wizard.run(self.root, io=FakeIO(["skip"] * 200 + []), only=["basics.currency", "basics.name"],
                   answers={"basics.currency": "USD"})
        self.assertIsNone(self.answers()["basics.name"])

    def test_resume_skips_answered(self):
        wizard.run(self.root, io=FakeIO([]), only=["basics.currency"], answers={"basics.currency": "EUR"})
        io = FakeIO(["Sam"])
        wizard.run(self.root, io=io, only=["basics.currency", "basics.name"])
        self.assertFalse(any("currency" in s.lower() and s.startswith("?") for s in io.shown))
        self.assertEqual(self.answers()["basics.name"], "Sam")
        self.assertEqual(self.answers()["basics.currency"], "EUR")

    def test_when_hides_finance_questions_if_domain_off(self):
        answers = {"domains.enabled": ["career"]}
        self.assertFalse(questions.applies(by_id("finance.income_monthly"), answers))
        answers["domains.enabled"].append("finance")
        self.assertTrue(questions.applies(by_id("finance.income_monthly"), answers))

    def test_invalid_time_reasks(self):
        io = FakeIO(["25:00", "7pm", "21:30"])
        wizard.run(self.root, io=io, only=["basics.currency", "rules.review_time"], answers={"basics.currency": "USD"})
        self.assertEqual(self.answers()["rules.review_time"], "21:30")
        self.assertTrue(any("HH:MM" in s for s in io.shown))

    def test_question_shows_why_example_skip(self):
        io = FakeIO(["Sam"])
        wizard.run(self.root, io=io, only=["basics.currency", "basics.name"], answers={"basics.currency": "USD"})
        text = "\n".join(io.shown)
        q = by_id("basics.name")
        for part in (q["why"], q["example"], q["skip"]):
            self.assertIn(part, text)

    def test_back_reasks_previous(self):
        io = FakeIO(["Sam", "back", "Alex", "skip"])
        wizard.run(self.root, io=io, only=["basics.currency", "basics.name", "basics.timezone"],
                   answers={"basics.currency": "USD"})
        self.assertEqual(self.answers()["basics.name"], "Alex")

    def test_answers_file_noninteractive(self):
        path = Path(self.temp.name) / "answers.json"
        path.write_text(json.dumps({"basics.currency": "INR", "basics.name": "Sam", "domains.enabled": ["finance"]}))
        wizard.run(self.root, io=FakeIO([]), answers_file=path, interactive=False)
        _, config = core.load(self.root)
        self.assertEqual(config["currency"], "INR")
        self.assertEqual(config["domains"], ["finance"])
        self.assertEqual(config["profile"]["name"], "Sam")

    def test_answers_file_is_validated(self):
        path = Path(self.temp.name) / "answers.json"
        path.write_text(json.dumps({"basics.currency": "INR", "rules.review_time": "99:99"}))
        with self.assertRaises(ValueError):
            wizard.run(self.root, io=FakeIO([]), answers_file=path, interactive=False)

    def test_existing_v1_workspace_is_migrated(self):
        core.init(self.root, "USD")
        config = json.loads((self.root / "life.json").read_text())
        config["schema_version"] = 1
        (self.root / "life.json").write_text(json.dumps(config))
        wizard.run(self.root, io=FakeIO([]), interactive=False)
        self.assertEqual(core.load(self.root)[1]["schema_version"], 2)
        self.assertEqual(self.answers()["basics.currency"], "USD")

    def test_secret_not_in_answers(self):
        secret_q = {"id": "test.token", "section": "basics", "prompt": "Token?", "why": "w", "example": "e",
                    "skip": "s", "kind": "secret", "secret_name": "test_token"}
        io = FakeIO(["s3cr3t-value-123"])
        with mock.patch.object(questions, "QUESTIONS", questions.QUESTIONS + [secret_q]):
            wizard.run(self.root, io=io, only=["basics.currency", "test.token"], answers={"basics.currency": "USD"})
        self.assertEqual(io.secret_prompts and True, True)
        raw = (self.root / ".local/setup-answers.json").read_text()
        self.assertNotIn("s3cr3t-value-123", raw)
        self.assertEqual(core.secret(self.root, "test_token"), "s3cr3t-value-123")
        self.assertNotIn("s3cr3t-value-123", "\n".join(io.shown))

    def test_cli_eof_saves_and_exits_cleanly(self):
        import subprocess, sys
        result = subprocess.run([sys.executable, "-m", "lifekit", "--workspace", str(self.root), "setup"],
                                input="usd\nSam\n", capture_output=True, text=True)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("run setup again", result.stderr)
        self.assertEqual(self.answers()["basics.name"], "Sam")
        self.assertLess(result.stdout.index("== Basics =="), result.stdout.index("currency"))

    def test_guide_matches_docs(self):
        docs = Path(__file__).resolve().parents[1] / "docs/setup-guide.md"
        self.assertEqual(questions.guide_markdown(), docs.read_text(encoding="utf-8"),
                         "Regenerate: python3 -m lifekit guide > docs/setup-guide.md")


if __name__ == "__main__":
    unittest.main()
