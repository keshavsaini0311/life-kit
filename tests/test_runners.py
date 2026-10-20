from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
import unittest

from lifekit import connections, core, runners


class FakeProc:
    """Stands in for subprocess.Popen; writes `output` to the stdout handle it was given."""

    def __init__(self, output=b"Report body", returncode=0, hang=False, calls=None):
        self.output, self.code, self.hang, self.calls = output, returncode, hang, calls
        self.killed = False

    def __call__(self, argv, **kwargs):
        self.argv, self.kwargs = argv, kwargs
        if self.calls is not None:
            self.calls.append(argv)
        self.pid = None
        return self

    def communicate(self, input=None, timeout=None):
        self.prompt = input
        if self.hang:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        self.kwargs["stdout"].write(self.output)
        self.returncode = self.code
        return None, None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.code


def missing(argv, **kwargs):
    raise FileNotFoundError(argv[0])


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = core.init(Path(self.temp.name) / "w", "USD")
        core.update_config(self.root, lambda c: c.update(domains=["learning", "work", "finance"],
                                                         assistants=["claude", "codex"], primary_assistant="codex"))

    def config(self):
        return core.load(self.root)[1]

    def test_available_filters_by_domain_and_connection(self):
        ids = runners.available(self.config())
        self.assertIn("nightly-report", ids)
        self.assertIn("learn", ids)
        self.assertNotIn("inbox-review", ids)  # needs gmail
        connections.write_configs(self.root, ["gmail"])
        self.assertIn("inbox-review", runners.available(self.config()))
        core.update_config(self.root, lambda c: c.update(domains=[]))
        self.assertNotIn("work-brief", runners.available(self.config()))

    def test_claude_command_allowlist_only_reads(self):
        connections.write_configs(self.root, ["gmail"])
        argv, assistant = runners.command(self.root, self.config(), "inbox-review")
        self.assertEqual(assistant, "claude")  # gmail is reachable headless only through Claude
        tools = argv[argv.index("--allowedTools") + 1].split(",")
        self.assertIn("mcp__claude_ai_Gmail__search_threads", tools)
        for forbidden in ("Write", "Edit", "Bash", "mcp__claude_ai_Gmail__send_message"):
            self.assertNotIn(forbidden, tools)

    def test_codex_command_read_only(self):
        connections.write_configs(self.root, ["github"])
        argv, assistant = runners.command(self.root, self.config(), "work-brief")
        self.assertEqual(assistant, "codex")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn("mcp_servers.github.url=\"https://api.githubcopilot.com/mcp/readonly\"", argv)
        self.assertIn("features.apps=false", argv)

    def test_codex_disables_unrelated_servers(self):
        (self.root / ".codex").mkdir(exist_ok=True)
        (self.root / ".codex/config.toml").write_text('[mcp_servers.shop]\nurl = "https://shop.example.com"\n')
        argv, _ = runners.command(self.root, self.config(), "nightly-report")
        self.assertIn("mcp_servers.shop.enabled=false", argv)

    def test_run_writes_report_and_status(self):
        proc = FakeProc()
        record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=proc)
        self.assertEqual(record["status"], "ok")
        report = (self.root / ".local/reports/2026-10-20-nightly-report.md").read_text()
        self.assertIn("Report body", report)
        self.assertIn("Local review", proc.prompt.decode())  # snapshot included in the prompt
        self.assertNotIn("LIFEKIT", " ".join(proc.argv))

    def test_same_slot_skips(self):
        runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=FakeProc())
        calls = []
        record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 23, 0), popen=FakeProc(calls=calls))
        self.assertEqual(record["status"], "skipped-done")
        self.assertEqual(calls, [])
        forced = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 23, 0), popen=FakeProc(), force=True)
        self.assertEqual(forced["status"], "ok")

    def test_second_slot_runs(self):
        connections.write_configs(self.root, ["gmail"])
        runners.run(self.root, "inbox-review", now=datetime(2026, 10, 20, 9, 5), popen=FakeProc())
        record = runners.run(self.root, "inbox-review", now=datetime(2026, 10, 20, 19, 5), popen=FakeProc())
        self.assertEqual(record["status"], "ok")

    def test_failed_run_retries_same_slot(self):
        runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=FakeProc(returncode=1))
        record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 30), popen=FakeProc())
        self.assertEqual(record["status"], "ok")

    def test_lock_held_skips(self):
        with runners.single_instance(self.root, "nightly-report") as acquired:
            self.assertTrue(acquired)
            record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=FakeProc())
        self.assertEqual(record["status"], "skipped-locked")

    def test_missing_agent(self):
        record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=missing)
        self.assertEqual(record["status"], "unavailable")
        self.assertTrue(list((self.root / ".local/reports").glob("*-7d.md")))

    def test_timeout_keeps_snapshot(self):
        proc = FakeProc(hang=True)
        record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=proc, timeout=1)
        self.assertEqual(record["status"], "timeout")
        self.assertTrue(proc.killed)
        self.assertTrue(list((self.root / ".local/reports").glob("*-7d.md")))

    def test_local_maintain_runs_without_agent(self):
        record = runners.run(self.root, "maintain", now=datetime(2026, 10, 20, 21, 46), popen=missing)
        self.assertEqual(record["status"], "ok")
        self.assertTrue((self.root / ".local/reports/maintenance-2026-10-20.md").is_file())

    def test_unknown_or_unavailable_runner_refused(self):
        with self.assertRaises(ValueError):
            runners.run(self.root, "inbox-review", now=datetime(2026, 10, 20, 9, 5), popen=FakeProc())
        with self.assertRaises(ValueError):
            runners.run(self.root, "nope", popen=FakeProc())

    def test_claude_runner_cannot_reach_write_tools(self):
        connections.write_configs(self.root, ["gmail"])
        argv, _ = runners.command(self.root, self.config(), "inbox-review")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        builtins = argv[argv.index("--tools") + 1].split(",")
        self.assertNotIn("Bash", builtins)
        self.assertNotIn("Write", builtins)
        self.assertIn("Bash", argv[argv.index("--disallowedTools") + 1].split(","))

    def test_ask_cannot_reach_write_tools(self):
        calls = []
        def run(argv, **kw):
            calls.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0, stdout="answer", stderr="")
        core.update_config(self.root, lambda c: c.update(primary_assistant="claude"))
        self.assertEqual(runners.ask(self.root, self.config(), "q?", run=run), "answer")
        argv, kw = calls[0]
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(kw["input"], "q?")
        self.assertNotIn("q?", argv)

    def test_slot_rechecked_after_lock(self):
        from contextlib import contextmanager
        real = runners.single_instance
        @contextmanager
        def finishes_first(root, rid):
            runners._save(self.root, rid, "2026-10-20 22:00", {"status": "ok"})  # another run finished meanwhile
            with real(root, rid) as acquired:
                yield acquired
        calls = []
        runners.single_instance = finishes_first
        try:
            record = runners.run(self.root, "nightly-report", now=datetime(2026, 10, 20, 22, 1), popen=FakeProc(calls=calls))
        finally:
            runners.single_instance = real
        self.assertEqual(record["status"], "skipped-done")
        self.assertEqual(calls, [])

    def test_failed_maintain_is_recorded(self):
        from unittest import mock
        with mock.patch.object(runners.maintain, "run", side_effect=ValueError("bad rules")):
            record = runners.run(self.root, "maintain", now=datetime(2026, 10, 20, 21, 46))
        self.assertEqual(record["status"], "failed")
        self.assertIn("bad rules", record["error"])

    def test_windows_resolves_cmd_shims(self):
        from unittest import mock
        with mock.patch.object(runners.shutil, "which", return_value="C:\\npm\\codex.cmd"):
            self.assertEqual(runners.resolve(["codex", "exec"])[0], "C:\\npm\\codex.cmd")


if __name__ == "__main__":
    unittest.main()
