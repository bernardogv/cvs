# CVS MCP server (typed tools, no raw shell)

A Model Context Protocol server that exposes the CVS JSON contract as **typed
tools** — the cleanest containment for an agent. It offers `describe`,
`list_suites`, `validate`, `preflight`, `run_test` (a *named* suite/case),
`results`, and `compare`, and **deliberately no "run arbitrary shell" tool**. An
agent on this server can discover, validate, and run named validation; it
*cannot* execute free-form commands on the fleet. For that you use the CLI's
`exec-json`, which keeps its human-approval gate.

Each tool shells the real `cvs … --format json` on the host and returns the
parsed contract, so it inherits structured output and structured errors for free.

## Run it

The server must run **where `cvs` can SSH every node** — normally the head node.

```bash
pip install mcp                 # the MCP SDK (only needed to run the server)
make install                    # ensure `cvs` is on PATH (or set CVS_BIN)
python -m cvs.mcp_server        # speaks MCP over stdio
```

`CVS_BIN` overrides the binary path (e.g. `CVS_BIN=/path/.cvs_venv/bin/cvs`).

## Register with Claude Code

```bash
claude mcp add cvs -- python -m cvs.mcp_server
# or, pinning the venv binary:
claude mcp add cvs --env CVS_BIN=/abs/path/.cvs_venv/bin/cvs -- python -m cvs.mcp_server
```

Then Claude drives the typed tools directly instead of shelling `cvs` through
Bash — same JSON contract, tighter blast radius.

The tool functions in `cvs/mcp_server.py` are plain Python and unit-tested
(`cvs/lib/unittests/test_mcp_server.py`) without the MCP runtime; the SDK is only
required to actually serve them.
