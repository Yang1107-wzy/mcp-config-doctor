import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLITests(unittest.TestCase):
    def run_cli(self, value, *args):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps(value), encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-m", "mcp_config_doctor", str(p), *args],
                capture_output=True,
                text=True,
            )

    def test_json_success(self):
        r = self.run_cli({"mcpServers": {"local": {"command": sys.executable}}}, "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["errors"], 0)

    def test_findings_exit_one(self):
        r = self.run_cli({"mcpServers": {"bad": {"args": "bad"}}}, "--format", "json")
        self.assertEqual(r.returncode, 1)
        self.assertGreater(json.loads(r.stdout)["errors"], 0)

    def test_warning_strict_mode(self):
        config = {"mcpServers": {"remote": {"url": "http://example.com/mcp"}}}
        self.assertEqual(self.run_cli(config).returncode, 0)
        self.assertEqual(self.run_cli(config, "--strict").returncode, 1)

    def test_malformed_json_exit_two(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("synthetic-private-data {")
            r = subprocess.run(
                [sys.executable, "-m", "mcp_config_doctor", str(p)], capture_output=True, text=True
            )
            self.assertEqual(r.returncode, 2)
            self.assertNotIn("synthetic-private-data", r.stderr)

    def test_inline_secret_never_printed(self):
        r = self.run_cli(
            {
                "mcpServers": {
                    "x": {
                        "url": "https://example.com",
                        "headers": {"Authorization": "synthetic-test-secret"},
                    }
                }
            },
            "--format",
            "json",
        )
        self.assertNotIn("synthetic-test-secret", r.stdout + r.stderr)

    def test_surrogate_name_is_safe_in_json_report(self):
        r = self.run_cli(
            {
                "mcpServers": {
                    "\ud800": {"url": "https://example.com", "headers": {"Authorization": "fake"}}
                }
            },
            "--format",
            "json",
        )
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["warnings"], 1)
