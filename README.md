# MCP Config Doctor

Catch broken MCP configuration before opening your client.

[![CI](https://github.com/Yang1107-wzy/mcp-config-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/Yang1107-wzy/mcp-config-doctor/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[中文说明](README.zh-CN.md) · [Releases](https://github.com/Yang1107-wzy/mcp-config-doctor/releases) · [Contributing](CONTRIBUTING.md)

![Example CLI output](docs/demo.svg)

A small offline preflight tool for JSON `mcpServers` and VS Code-style `servers` files. It checks executable availability, argument types, transport mismatches, HTTP URL syntax, environment placeholders and literal credential-like values. It never starts your servers or connects to their URLs.

## Install

Python 3.10+; no runtime dependencies. The project is distributed on GitHub, not PyPI.

```sh
python -m pip install "git+https://github.com/Yang1107-wzy/mcp-config-doctor.git@v1.0.0"
mcp-config-doctor --version
```

Alternatively download the wheel from [Releases](https://github.com/Yang1107-wzy/mcp-config-doctor/releases) and run `python -m pip install path/to/downloaded.whl` with its actual filename.

To run the bundled examples:

```sh
git clone https://github.com/Yang1107-wzy/mcp-config-doctor.git
cd mcp-config-doctor
python -m pip install .
```

## Try it

```sh
mcp-config-doctor examples/good.json
mcp-config-doctor examples/broken.json --format json
mcp-config-doctor examples/broken.json --strict
```

The good example exits 0. The broken example exits 1 with `command-not-found`, `invalid-args`, `missing-env` and `insecure-http` findings. Reports contain diagnostics rather than argument, header or environment values.

## Checks

| Check | Result |
| --- | --- |
| Non-object root/server, ambiguous root, duplicate JSON properties | Error |
| Missing executable on the current machine's PATH | Error |
| Non-string command, args, env or header values | Error |
| Both command and URL; declared transport conflicts | Error |
| Invalid HTTP(S) URL, port, embedded URL credentials | Error |
| Unset `${NAME}` / `${env:NAME}` | Error |
| Literal value under a credential-like env/header key | Warning |
| HTTP outside loopback | Warning |
| `${input:NAME}` or unsupported placeholder syntax | Warning |
| `disabled: true` | Skip |

## Example configuration

```json
{
  "mcpServers": {
    "search": {
      "command": "python",
      "args": ["server.py"],
      "env": {"API_KEY": "${env:SEARCH_API_KEY}"}
    }
  }
}
```

Placeholder expansion differs between clients. This tool checks references against the **current process environment**; it resolves known environment references in memory for URL validation but does not rewrite the file or promise that a particular client supports the same syntax. Prefer the reference syntax your client documents. The environment of a GUI client may differ from your terminal's PATH and variables.

## Automation

```sh
mcp-config-doctor .mcp.json --strict --format json > mcp-report.json
```

| Exit | Meaning |
| --- | --- |
| 0 | No errors; warnings allowed unless `--strict` |
| 1 | Findings fail the check |
| 2 | Usage, file or JSON parse failure; stderr diagnostic |

JSON output uses `schema_version: 1`, `servers`, `skipped`, `errors`, `warnings` and `findings`. Findings contain `server`, `severity`, `code` and `message`. Server names and environment variable names are included; secret **values** are not. Do not put secrets in identifiers.

## Scope and limitations

This checks JSON client configuration, not MCP protocol conformance or runtime health. It cannot verify OAuth, remote server availability, executable behavior, package installation, arguments specific to a server, or whether a script file exists. It does not support JSONC, TOML, automatic client discovery or client-specific `inputs` definitions. Literal-secret checks are name heuristics, not a complete secret scanner.

For live protocol inspection, use the official [MCP Inspector](https://github.com/modelcontextprotocol/inspector). Transport concepts follow the [MCP transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports); client configuration layouts are conventions, not part of that transport specification. This implementation is independent and is not affiliated with the MCP project.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

CI runs on Linux, Windows and macOS. All examples use synthetic inputs. [MIT license](LICENSE).
