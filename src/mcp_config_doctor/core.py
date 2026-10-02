"""Offline checks for JSON MCP client configuration. Never launches a server."""

import ipaddress
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

PLACEHOLDER = re.compile(r"\$\{(?:(env|input):)?([A-Za-z_][A-Za-z0-9_]*)\}")
SENSITIVE = re.compile(r"token|secret|password|api[_-]?key|authorization", re.I)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property; remove ambiguous entries.")
        result[key] = value
    return result


def load_config(path):
    """Read strict JSON; error messages never include configuration contents."""
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON number.")),
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}.") from None
    except UnicodeError:
        raise ValueError("Configuration must be UTF-8.") from None


def inspect_config(config, *, environ=None, which=None):
    """Return a JSON-serializable report without copying argument or secret values."""
    environ = os.environ if environ is None else environ
    which = shutil.which if which is None else which
    report = {
        "schema_version": 1,
        "servers": 0,
        "skipped": 0,
        "errors": 0,
        "warnings": 0,
        "findings": [],
    }

    def add(server, severity, code, message):
        report["findings"].append(
            {"server": server, "severity": severity, "code": code, "message": message}
        )
        report["errors" if severity == "error" else "warnings"] += 1

    if not isinstance(config, dict):
        add(None, "error", "invalid-root", "The configuration root must be an object.")
        return report
    roots = [key for key in ("mcpServers", "servers") if key in config]
    if len(roots) != 1 or not isinstance(config.get(roots[0]) if roots else None, dict):
        add(None, "error", "invalid-root", "Provide exactly one mcpServers or servers object.")
        return report
    servers = config[roots[0]]
    report["servers"] = len(servers)
    if not servers:
        add(None, "warning", "empty-config", "No servers are configured.")
    for name, server in servers.items():
        if not isinstance(server, dict):
            add(name, "error", "invalid-server", "Each server must be an object.")
            continue
        if "disabled" in server and not isinstance(server["disabled"], bool):
            add(name, "error", "invalid-disabled", "disabled must be a boolean.")
        if server.get("disabled") is True:
            report["skipped"] += 1
            continue
        kind = server.get("type")
        if kind not in (None, "stdio", "http", "sse"):
            add(name, "error", "unknown-transport", "Supported types are stdio, http and sse.")
        cmd, url = server.get("command"), server.get("url")
        if "command" in server and "url" in server:
            add(
                name,
                "error",
                "mixed-transport",
                "Use command for stdio or url for remote transport.",
            )
        if kind == "stdio" and "url" in server or kind in ("http", "sse") and "command" in server:
            add(name, "error", "transport-mismatch", "The type conflicts with command or url.")
        if kind in ("http", "sse") and "url" not in server:
            add(name, "error", "missing-url", "Remote transport requires a url.")
        elif "command" not in server and "url" not in server:
            add(name, "error", "missing-command", "A command or url is required.")

        def check_template(value, name=name):
            for match in PLACEHOLDER.finditer(value):
                category, key = match.groups()
                if category == "input":
                    add(
                        name,
                        "warning",
                        "client-input",
                        "A client input placeholder cannot be checked offline.",
                    )
                elif not environ.get(key):
                    add(
                        name,
                        "error",
                        "missing-env",
                        f"Environment variable {key} is unset or empty.",
                    )
            if "${" in PLACEHOLDER.sub("", value):
                add(
                    name, "warning", "unknown-placeholder", "A placeholder uses unsupported syntax."
                )

        if "command" in server:
            if not isinstance(cmd, str) or not cmd.strip():
                add(name, "error", "invalid-command", "command must be a nonempty string.")
            else:
                check_template(cmd)
                if "${" not in cmd and not which(os.path.expanduser(cmd)):
                    add(
                        name,
                        "error",
                        "command-not-found",
                        "Command is not executable or is absent from the current PATH.",
                    )
            args = server.get("args", [])
            if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
                add(name, "error", "invalid-args", "args must be an array of strings.")
            else:
                for arg in args:
                    check_template(arg)
        for field in ("env", "headers"):
            values = server.get(field, {})
            if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
                add(name, "error", "invalid-" + field, f"{field} must map names to strings.")
                continue
            for key, value in values.items():
                check_template(value)
                if value and SENSITIVE.search(key) and "${" not in value:
                    add(
                        name,
                        "warning",
                        "inline-secret",
                        f"{field} contains a literal credential-like value; prefer client-supported variable references.",
                    )
        if "url" in server:
            if not isinstance(url, str) or not url.strip():
                add(name, "error", "invalid-url", "url must be a nonempty HTTP(S) URL.")
                continue
            check_template(url)

            def resolve_url(match, url=url):
                if match[1] == "input":
                    # Unknown inputs remain warnings, with syntax-safe stand-ins.
                    if url == match[0]:
                        return "https://placeholder.invalid"
                    if ":" + match[0] in url and "://" + match[0] not in url:
                        return "443"
                    return "placeholder"
                return environ.get(match[2], "placeholder")

            resolved = PLACEHOLDER.sub(resolve_url, url)
            try:
                parts = urlsplit(resolved)
                port = parts.port  # Validate port syntax and bounds.
                del port
                if (
                    parts.scheme not in ("http", "https")
                    or not parts.hostname
                    or any(c.isspace() for c in resolved)
                ):
                    raise ValueError
                if parts.username is not None or parts.password is not None:
                    add(
                        name,
                        "error",
                        "url-credentials",
                        "Move embedded URL credentials to client-supported authentication.",
                    )
                try:
                    loopback = ipaddress.ip_address(parts.hostname).is_loopback
                except ValueError:
                    loopback = parts.hostname.lower() == "localhost"
                if parts.scheme == "http" and not loopback:
                    add(
                        name,
                        "warning",
                        "insecure-http",
                        "Remote HTTP traffic is unencrypted; consider HTTPS.",
                    )
            except ValueError:
                add(
                    name,
                    "error",
                    "invalid-url",
                    "url must have an HTTP(S) scheme, host and valid port.",
                )
    return report
