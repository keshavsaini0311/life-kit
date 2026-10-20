import os
from pathlib import Path
import tempfile
import unittest

from lifekit import core, render

FULL = {
    "basics.currency": "USD", "basics.name": "Sam", "basics.timezone": "Europe/London",
    "domains.enabled": ["personal", "finance", "career", "work"],
    "rules.work_hours": "Mon-Fri 9-6", "rules.free_time": "1h after dinner", "rules.review_time": "21:30",
    "rules.privacy": None, "rules.tone": "Direct",
    "personal.goals": "Run a 10k", "personal.routine": None, "personal.notes": None,
    "finance.income_monthly": "5000", "finance.baseline_spend": "3000", "finance.goals": None, "finance.bank_csv": True,
    "career.current_role": "Backend engineer", "career.target": "Senior in 1 year", "career.locations": "Remote",
    "career.resume_path": None, "career.prep_topics": "System design",
    "work.employer": "Example Co, engineer", "work.tools": ["github", "slack"], "work.standup_time": "10:00",
    "assistants.enabled": ["claude", "codex"], "assistants.primary": "claude",
}


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = core.init(Path(self.temp.name) / "w", "USD")

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def test_apply_writes_core_files(self):
        written = render.apply(self.root, FULL)
        for rel in ("AGENTS.md", "CLAUDE.md", "LIFE.md", "personal/rules.md", "memory/MEMORY.md",
                    "personal/context.md", "finance/context.md", "finance/rules.json", "career/context.md",
                    "career/job-search/tracker.md", "career/prep/plan.md", "work/context.md", "work/standup.md"):
            self.assertTrue((self.root / rel).is_file(), rel)
        self.assertIn("personal/rules.md", written)
        self.assertIn("Sam", self.read("personal/rules.md"))
        self.assertIn("21:30", self.read("personal/rules.md"))
        self.assertIn("5000 USD", self.read("finance/context.md"))
        self.assertTrue((self.root / "finance/inbox").is_dir())

    def test_skipped_answer_renders_unknown(self):
        render.apply(self.root, FULL)
        self.assertIn("Privacy: unknown", self.read("personal/rules.md"))

    def test_rerun_keeps_edits(self):
        render.apply(self.root, FULL)
        (self.root / "personal/rules.md").write_text("my own rules\n")
        changed = dict(FULL, **{"rules.tone": "Gentle"})
        written = render.apply(self.root, changed)
        self.assertEqual(self.read("personal/rules.md"), "my own rules\n")
        self.assertIn("Gentle", self.read("personal/rules.md.suggested"))
        self.assertIn("personal/rules.md.suggested", written)

    def test_rerun_updates_unedited_files(self):
        render.apply(self.root, FULL)
        render.apply(self.root, dict(FULL, **{"rules.tone": "Gentle"}))
        self.assertIn("Gentle", self.read("personal/rules.md"))
        self.assertFalse((self.root / "personal/rules.md.suggested").exists())

    def test_skills_follow_domains(self):
        render.apply(self.root, dict(FULL, **{"domains.enabled": ["finance"]}))
        skills = {p.name for p in (self.root / ".agents/skills").iterdir()}
        self.assertIn("finance", skills)
        self.assertIn("life", skills)
        self.assertNotIn("job-hunt", skills)
        self.assertNotIn("work", skills)

    def test_claude_skills_points_to_agents(self):
        render.apply(self.root, FULL)
        link = self.root / ".claude/skills"
        self.assertTrue((link / "finance/SKILL.md").is_file())
        if link.is_symlink():
            self.assertEqual(os.readlink(str(link)), os.path.join("..", ".agents", "skills"))

    def test_outreach_skills_say_drafts_only(self):
        render.apply(self.root, FULL)
        for name in ("hiring-outreach", "apply-autofill", "find-contact", "job-hunt"):
            text = self.read(".agents/skills/" + name + "/SKILL.md").lower()
            self.assertIn("draft", text, name)
            self.assertTrue("never send" in text or "never submit" in text, name)

    def test_templates_have_no_unfilled_placeholders(self):
        # strict string.Template substitution raises on any unknown $placeholder
        render.apply(self.root, FULL)
        for path in (self.root / ".agents/skills").rglob("SKILL.md"):
            self.assertNotIn("$workspace", path.read_text(), path)

    def test_no_domains_still_writes_core(self):
        render.apply(self.root, {"basics.currency": "USD", "domains.enabled": []})
        self.assertTrue((self.root / "LIFE.md").is_file())
        self.assertTrue((self.root / ".agents/skills/life-review/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
