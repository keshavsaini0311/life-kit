from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

from lifekit import core, questions, schedule


def recorder(calls, crontab=""):
    def run(argv, **kwargs):
        calls.append((argv, kwargs.get("input")))
        if argv[:2] == ["crontab", "-l"]:
            return subprocess.CompletedProcess(argv, 0, stdout=crontab, stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    return run


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.root = core.init(Path(self.temp.name) / "w", "USD")
        core.update_config(self.root, lambda c: c.update(domains=["work", "career"], connections={"github": {}}))
        schedule.set_runner(self.root, "work-brief", "08:30", "weekdays")
        schedule.set_runner(self.root, "nightly-report", "22:15", "daily")

    def jobs(self):
        return schedule.jobs(self.root, core.load(self.root)[1])

    def test_only_enabled_available_runners_become_jobs(self):
        labels = {j["runner"] for j in self.jobs()}
        self.assertEqual(labels, {"work-brief", "nightly-report"})

    def test_launchd_plist_times_weekdays(self):
        actions = schedule.plan(self.jobs(), "darwin", self.home)
        plist = next(a for a in actions if a.get("path") and "work-brief" in str(a["path"]))
        data = plistlib.loads(plist["content"].encode())
        self.assertEqual(len(data["StartCalendarInterval"]), 5)
        self.assertEqual(data["StartCalendarInterval"][0], {"Hour": 8, "Minute": 30, "Weekday": 1})
        self.assertIn("PATH", data["EnvironmentVariables"])
        self.assertEqual(data["ProgramArguments"][-2:], ["run", "work-brief"])
        self.assertTrue(str(plist["path"]).startswith(str(self.home / "Library/LaunchAgents")))

    def test_systemd_oncalendar(self):
        actions = schedule.plan(self.jobs(), "linux", self.home, systemd=True)
        timer = next(a for a in actions if str(a.get("path", "")).endswith("work-brief.timer"))
        self.assertIn("OnCalendar=Mon..Fri *-*-* 08:30:00", timer["content"])
        self.assertIn("Persistent=true", timer["content"])
        self.assertIn(".config/systemd/user", str(timer["path"]))

    def test_cron_block_replaced_not_duplicated(self):
        calls = []
        existing = "0 7 * * * echo mine\n"
        schedule.install(self.root, run=recorder(calls, existing), platform="linux", home=self.home, systemd=False)
        written = [i for a, i in calls if a == ["crontab", "-"]][-1]
        self.assertIn("echo mine", written)
        self.assertIn("30 8 * * 1-5 ", written)
        calls2 = []
        schedule.install(self.root, run=recorder(calls2, written), platform="linux", home=self.home, systemd=False)
        again = [i for a, i in calls2 if a == ["crontab", "-"]][-1]
        self.assertEqual(again.count("# BEGIN life-kit"), 1)
        self.assertEqual(again.count("work-brief"), 1)

    def test_schtasks_args(self):
        actions = schedule.plan(self.jobs(), "win32", self.home)
        commands = [a["command"] for a in actions if a.get("command")]
        weekly = next(c for c in commands if any("work-brief" in x for x in c))
        self.assertEqual(weekly[:3], ["schtasks", "/Create", "/F"])
        self.assertIn("/SC", weekly)
        self.assertEqual(weekly[weekly.index("/SC") + 1], "WEEKLY")
        self.assertEqual(weekly[weekly.index("/D") + 1], "MON,TUE,WED,THU,FRI")
        self.assertEqual(weekly[weekly.index("/ST") + 1], "08:30")

    def test_labels_differ_per_workspace(self):
        other = core.init(Path(self.temp.name) / "w2", "USD")
        self.assertNotEqual(schedule.label(self.root, "maintain"), schedule.label(other, "maintain"))

    def test_set_rejects_bad_time(self):
        for bad in ("8:30", "24:00", "noon"):
            with self.assertRaises(ValueError):
                schedule.set_runner(self.root, "work-brief", bad, "daily")
        with self.assertRaises(ValueError):
            schedule.set_runner(self.root, "work-brief", "08:00", "someday")

    def test_install_dry_run_touches_nothing(self):
        calls = []
        text = schedule.install(self.root, dry_run=True, run=recorder(calls), platform="darwin", home=self.home)
        self.assertEqual(calls, [])
        self.assertEqual(list(self.home.rglob("*")), [])
        self.assertIn("work-brief", "\n".join(text))

    def test_install_then_remove_launchd(self):
        calls = []
        schedule.install(self.root, run=recorder(calls), platform="darwin", home=self.home)
        agents = list((self.home / "Library/LaunchAgents").glob("*.plist"))
        self.assertEqual(len(agents), 2)
        self.assertTrue(any(c[0][:2] == ["launchctl", "bootstrap"] for c in calls))
        schedule.remove(self.root, run=recorder([]), platform="darwin", home=self.home)
        self.assertEqual(list((self.home / "Library/LaunchAgents").glob("*.plist")), [])

    def test_schedule_answer_parsing(self):
        q = {"id": "x", "kind": "schedule"}
        self.assertEqual(questions.parse(q, "08:30,19:00 weekdays"), {"times": ["08:30", "19:00"], "days": "weekdays"})
        self.assertEqual(questions.parse(q, "22:00"), {"times": ["22:00"], "days": "daily"})
        with self.assertRaises(ValueError):
            questions.parse(q, "8pm")

    def test_wizard_answers_set_runner_times(self):
        from lifekit import wizard
        root = Path(self.temp.name) / "fresh"
        wizard.run(root, interactive=False, answers={
            "basics.currency": "USD", "domains.enabled": ["career"], "rules.review_time": "21:00",
            "runners.selected": ["nightly-report", "job-discovery"], "runner.job-discovery": "07:15 weekdays"})
        config = core.load(root)[1]
        self.assertEqual(config["runners"]["job-discovery"], {"enabled": True, "times": ["07:15"], "days": "weekdays"})
        self.assertFalse(config["runners"]["learn"]["enabled"])
        self.assertTrue(config["runners"]["nightly-report"]["enabled"])


if __name__ == "__main__":
    unittest.main()
