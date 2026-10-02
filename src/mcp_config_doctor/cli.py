"""Command line interface for MCP configuration preflight."""

import argparse
import json
import sys

from . import __version__
from .core import inspect_config, load_config


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check MCP JSON configuration without starting servers."
    )
    parser.add_argument("config", help="JSON file with mcpServers or servers")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        report = inspect_config(load_config(args.config))
    except (OSError, ValueError, RecursionError) as exc:
        if isinstance(exc, OSError):
            message = "Cannot read configuration file."
        elif isinstance(exc, RecursionError):
            message = "JSON nesting is too deep."
        else:
            message = str(exc)
        print("mcp-config-doctor: " + message, file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(
            f"{report['servers']} servers | {report['errors']} errors | {report['warnings']} warnings | {report['skipped']} disabled"
        )
        for item in report["findings"]:
            # JSON encoding prevents config-controlled names from emitting terminal escape codes.
            name = json.dumps(item["server"], ensure_ascii=True)
            print(f"{item['severity'].upper()} [{item['code']}] {name}: {item['message']}")
    return int(bool(report["errors"] or args.strict and report["warnings"]))
