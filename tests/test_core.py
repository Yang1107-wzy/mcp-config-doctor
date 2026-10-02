import json
import os
import tempfile
import unittest
from pathlib import Path

from mcp_config_doctor.core import inspect_config


class ConfigTests(unittest.TestCase):
    def inspect(self, value, env=None):
        return inspect_config(
            value, environ=env or {}, which=lambda x: "/bin/x" if x == "python" else None
        )

    def codes(self, result):
        return {x["code"] for x in result["findings"]}

    def test_valid_stdio(self):
        r = self.inspect({"mcpServers": {"demo": {"command": "python", "args": ["app.py"]}}})
        self.assertEqual(r["errors"], 0)
        self.assertEqual(r["servers"], 1)

    def test_vscode_servers(self):
        self.assertEqual(
            self.inspect({"servers": {"demo": {"type": "http", "url": "https://example.com/mcp"}}})[
                "errors"
            ],
            0,
        )

    def test_missing_command(self):
        self.assertIn(
            "command-not-found",
            self.codes(self.inspect({"mcpServers": {"x": {"command": "missing"}}})),
        )

    def test_args_are_array_of_strings(self):
        for args in ["-y demo", [1], None]:
            with self.subTest(args=args):
                self.assertIn(
                    "invalid-args",
                    self.codes(
                        self.inspect({"mcpServers": {"x": {"command": "python", "args": args}}})
                    ),
                )

    def test_resolved_env_placeholder(self):
        self.assertNotIn(
            "missing-env",
            self.codes(
                self.inspect(
                    {"mcpServers": {"x": {"command": "python", "env": {"TOKEN": "${TOKEN}"}}}},
                    {"TOKEN": "fake"},
                )
            ),
        )

    def test_unresolved_env_does_not_print_values(self):
        cfg = {
            "mcpServers": {
                "x": {
                    "command": "python",
                    "env": {"TOKEN": "${TOKEN}", "API_KEY": "synthetic-secret"},
                }
            }
        }
        r = self.inspect(cfg)
        self.assertIn("missing-env", self.codes(r))
        self.assertIn("inline-secret", self.codes(r))
        self.assertNotIn("synthetic-secret", json.dumps(r))

    def test_invalid_env_shape(self):
        self.assertIn(
            "invalid-env",
            self.codes(self.inspect({"mcpServers": {"x": {"command": "python", "env": ["oops"]}}})),
        )

    def test_mixed_transport(self):
        self.assertIn(
            "mixed-transport",
            self.codes(
                self.inspect(
                    {"mcpServers": {"x": {"command": "python", "url": "https://example.com"}}}
                )
            ),
        )

    def test_invalid_url_and_port(self):
        for url in [
            "ftp://example.com",
            "https://",
            "https://example.com:bad",
            "https://u:p@example.com",
        ]:
            with self.subTest(url=url):
                self.assertGreater(self.inspect({"mcpServers": {"x": {"url": url}}})["errors"], 0)

    def test_http_warning_only_non_loopback(self):
        for host, expected in [
            ("localhost", False),
            ("127.0.0.1", False),
            ("[::1]", False),
            ("example.com", True),
        ]:
            r = self.inspect({"mcpServers": {"x": {"url": f"http://{host}/mcp"}}})
            self.assertEqual("insecure-http" in self.codes(r), expected)

    def test_disabled_server_skipped(self):
        r = self.inspect({"mcpServers": {"x": {"disabled": True}}})
        self.assertEqual(r["errors"], 0)
        self.assertEqual(r["skipped"], 1)

    def test_root_shapes(self):
        for value in [[], {}, {"mcpServers": []}, {"mcpServers": {"x": None}}]:
            self.assertGreater(self.inspect(value)["errors"], 0)

    def test_header_placeholders(self):
        r = self.inspect(
            {
                "mcpServers": {
                    "x": {
                        "url": "https://example.com",
                        "headers": {"Authorization": "Bearer ${env:KEY}"},
                    }
                }
            }
        )
        self.assertIn("missing-env", self.codes(r))

    def test_file_loading_rejects_duplicates(self):
        from mcp_config_doctor.core import load_config

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text('{"mcpServers":{},"mcpServers":{}}')
            with self.assertRaises(ValueError):
                load_config(p)

    def test_command_path_is_checked_without_running(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ("tool.cmd" if os.name == "nt" else "tool")
            p.write_text("this must never execute")
            os.chmod(p, 0o700)
            self.assertEqual(
                inspect_config({"mcpServers": {"x": {"command": str(p)}}})["errors"], 0
            )

    def test_placeholder_url_does_not_hide_bad_scheme_or_port(self):
        for url in ["ftp://${env:HOST}/mcp", "https://example.com:99999/${env:TOKEN}"]:
            r = self.inspect(
                {"mcpServers": {"x": {"url": url}}}, {"HOST": "example.com", "TOKEN": "fake"}
            )
            self.assertIn("invalid-url", self.codes(r))

    def test_client_input_url_remains_warning(self):
        for url in ["https://example.com:${input:PORT}/mcp", "${input:MCP_URL}"]:
            r = self.inspect({"mcpServers": {"x": {"url": url}}})
            self.assertEqual(r["errors"], 0)
            self.assertIn("client-input", self.codes(r))
