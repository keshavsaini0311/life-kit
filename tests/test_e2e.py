import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lifekit import core, schedule

REPO = Path(__file__).resolve().parents[1]


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "life"

    def setup_cli(self, *extra):
        return subprocess.run([sys.executable, "-m", "lifekit", "--workspace", str(self.root), "setup",
                               "--answers", str(REPO / "examples/answers.json")] + list(extra),
                              capture_output=True, text=True, cwd=str(REPO))

    def test_full_setup_from_answers_file(self):
        result = self.setup_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel in ("personal/rules.md", "LIFE.md", "AGENTS.md", "CLAUDE.md", "memory/MEMORY.md",
                    ".agents/skills/job-hunt/SKILL.md", ".claude/skills/finance/SKILL.md",
                    ".mcp.json", ".codex/config.toml", "finance/rules.json", "career/job-search/tracker.md"):
            self.assertTrue((self.root / rel).exists(), rel)
        config = core.load(self.root)[1]
        self.assertEqual(config["runners"]["inbox-review"]["times"], ["09:00", "18:30"])
        self.assertEqual(config["runners"]["nightly-report"]["times"], ["21:30"])
        self.assertEqual(set(config["connections"]), {"gmail", "github"})
        plan = "\n".join(schedule.install(self.root, dry_run=True, platform="darwin", home=Path(self.temp.name) / "home"))
        for rid in ("maintain", "nightly-report", "inbox-review"):
            self.assertIn(rid, plan)
        self.assertFalse((Path(self.temp.name) / "home").exists())

    def test_summary_separates_configured_and_verified(self):
        out = self.setup_cli().stdout
        self.assertIn("Setup summary", out)
        self.assertIn("gmail: configured, not verified", out)
        self.assertIn("inbox-review: 09:00,18:30 daily (saved, not installed)", out)
        self.assertIn("life-kit --workspace", out)

    def test_rerun_is_idempotent(self):
        self.setup_cli()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".local" not in p.parts}
        self.assertEqual(self.setup_cli().returncode, 0)
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".local" not in p.parts}
        changed = [str(p) for p in before if before[p] != after.get(p)]
        self.assertEqual(changed, [])
        self.assertFalse(list(self.root.rglob("*.suggested")))

    def test_setup_works_on_a_non_utf8_console(self):
        # Windows consoles often use cp1252, which cannot encode arrows or dashes in our messages.
        import os
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        result = subprocess.run([sys.executable, "-m", "lifekit", "--workspace", str(self.root), "setup",
                                 "--answers", str(REPO / "examples/answers.json")],
                                capture_output=True, cwd=str(REPO), env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode("cp1252", "replace"))
        self.assertIn(b"Setup summary", result.stdout)

    def test_doctor_reports_connections_and_schedules(self):
        self.setup_cli()
        result = subprocess.run([sys.executable, "-m", "lifekit", "--workspace", str(self.root), "doctor"],
                                capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("github: configured, not verified", result.stdout)
        self.assertIn("Scheduled jobs: not installed", result.stdout)


if __name__ == "__main__":
    unittest.main()
