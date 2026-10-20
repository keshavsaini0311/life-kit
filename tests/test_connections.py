import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from lifekit import catalog, connections, core

FAKE_TOKEN = "ghp" + "_" + "x" * 36  # split so the publication guard stays strict


def fake_run(stdout="", returncode=0, raises=None, capture=None):
    def run(argv, **kwargs):
        if capture is not None:
            capture.append((argv, kwargs))
        if raises:
            raise raises
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")
    return run


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = core.init(Path(self.temp.name) / "w", "USD")

    def test_every_entry_has_login_verify_docs(self):
        ids = set()
        for entry in catalog.CONNECTIONS:
            for key in ("id", "title", "domains", "source", "docs", "login", "read_tools", "headless"):
                self.assertTrue(entry.get(key) is not None and entry.get(key) != "", entry["id"] + " " + key)
            self.assertIn(entry["source"], ("official", "community", "account", "custom"))
            self.assertTrue(entry["docs"].startswith("https://"), entry["id"])
            self.assertNotIn(entry["id"], ids)
            ids.add(entry["id"])
            if entry.get("verify"):
                self.assertIn(entry["verify"]["tool"], entry["read_tools"], entry["id"])
        for plugin in catalog.PLUGINS:
            self.assertTrue(plugin["install"].startswith("claude plugin install "), plugin["id"])

    def test_mcp_json_uses_env_refs_not_secrets(self):
        core.save_secret(self.root, "github_token", FAKE_TOKEN)
        connections.write_configs(self.root, ["github"])
        text = (self.root / ".mcp.json").read_text()
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertIn("${LIFEKIT_GITHUB_TOKEN}", text)
        self.assertNotIn(FAKE_TOKEN[:12], (self.root / ".codex/config.toml").read_text())
        env = (self.root / ".local/env.sh").read_text()
        self.assertIn("LIFEKIT_GITHUB_TOKEN", env)

    def test_codex_toml_limits_tools(self):
        connections.write_configs(self.root, ["github"])
        text = (self.root / ".codex/config.toml").read_text()
        self.assertIn("[mcp_servers.github]", text)
        self.assertIn("enabled_tools = [", text)

    def test_write_configs_keeps_existing_servers(self):
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"type": "http", "url": "https://x.example.com"}}}))
        (self.root / ".codex").mkdir()
        (self.root / ".codex/config.toml").write_text('[mcp_servers.mine]\nurl = "https://x.example.com"\n')
        connections.write_configs(self.root, ["github"])
        connections.write_configs(self.root, ["github"])
        servers = json.loads((self.root / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(set(servers), {"mine", "github"})
        text = (self.root / ".codex/config.toml").read_text()
        self.assertIn("[mcp_servers.mine]", text)
        self.assertEqual(text.count("[mcp_servers.github]"), 1)

    def test_account_connector_not_written_to_mcp_json(self):
        connections.write_configs(self.root, ["gmail"])
        servers = json.loads((self.root / ".mcp.json").read_text())["mcpServers"]
        self.assertNotIn("gmail", servers)
        self.assertIn("gmail", core.load(self.root)[1]["connections"])

    def test_verify_ok_records_last_read(self):
        connections.write_configs(self.root, ["github"])
        calls = []
        record = connections.verify(self.root, "github", "claude",
                                    run=fake_run(json.dumps({"result": "OK"}), capture=calls))
        self.assertEqual(record["status"], "ok")
        self.assertTrue(record["authenticated"])
        self.assertIsNotNone(record["last_read_at"])
        argv = calls[0][0]
        self.assertIn("--allowedTools", argv)
        self.assertIn("mcp__github__get_me", argv)
        self.assertEqual(connections.status(self.root)["github"]["status"], "ok")

    def test_verify_auth_failure_is_expired(self):
        connections.write_configs(self.root, ["github"])
        record = connections.verify(self.root, "github", "claude", run=fake_run(json.dumps({"result": "AUTH"})))
        self.assertEqual(record["status"], "expired")
        self.assertFalse(record["authenticated"])
        self.assertIsNone(record["last_read_at"])

    def test_verify_missing_cli_is_absent_not_ok(self):
        connections.write_configs(self.root, ["github"])
        record = connections.verify(self.root, "github", "codex", run=fake_run(raises=FileNotFoundError("codex")))
        self.assertEqual(record["status"], "unavailable")
        self.assertEqual(record["error"], "absent")
        self.assertTrue(record["configured"])

    def test_verify_error_is_category_only(self):
        connections.write_configs(self.root, ["github"])
        leak = "token " + FAKE_TOKEN + " rejected"
        connections.verify(self.root, "github", "claude", run=fake_run(leak, returncode=1))
        raw = (self.root / ".local/connections.json").read_text()
        self.assertNotIn(FAKE_TOKEN, raw)
        self.assertIn('"error": "tool"', raw)

    def test_verify_unconfigured_refuses(self):
        with self.assertRaises(ValueError):
            connections.verify(self.root, "github", "claude", run=fake_run("{}"))

    def test_cli_add_custom_server(self):
        from lifekit import cli
        code = cli.main(["--workspace", str(self.root), "connect", "add-custom", "team-kb",
                         "--url", "https://kb.example.com/mcp", "--read-tools", "search", "--verify-tool", "search"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.root / ".mcp.json").read_text())["mcpServers"]["team-kb"]["url"],
                         "https://kb.example.com/mcp")
        self.assertEqual(connections.entry(self.root, "team-kb")["verify"]["tool"], "search")


if __name__ == "__main__":
    unittest.main()
