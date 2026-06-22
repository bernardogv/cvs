'''Typed MCP server over the CVS JSON contract — the cleanest containment.

It exposes a small set of TYPED tools (describe, list, validate, preflight, run a
*named* test, results, compare) and **deliberately no "run arbitrary shell"
tool** — an agent driving this server can validate and run named suites but
cannot execute free-form commands on the fleet (for that, use the CLI's
`exec-json` with its human-approval gate). Every tool shells the real `cvs ...
--format json` and returns the parsed contract, so the server inherits the
engine's structured output (including structured errors) for free.

Run it (on the head node, where `cvs` can SSH the cluster):
    python -m cvs.mcp_server          # speaks MCP over stdio
Register it with Claude Code via `claude mcp add` (see cvs/mcp/README.md).

The tool functions below are plain and unit-testable; the MCP SDK wiring in
main() is a thin, import-guarded layer so the logic is covered without the
runtime installed.
'''

import json
import os
import subprocess

# Default to `cvs` on PATH; override for an out-of-PATH venv install.
CVS_BIN = os.environ.get('CVS_BIN', 'cvs')

# The exposed surface — names only. Asserted in tests: no 'exec'/'shell'/'run'
# (arbitrary) entry, by design. Mutating but *named* operations (run_test) are
# allowed; arbitrary remote execution is not.
TOOLS = ('describe', 'list_suites', 'validate', 'preflight', 'run_test', 'results', 'compare')


def cvs_json(command_args, timeout=900, want_format=True):
    '''Run ``cvs <command_args> [--format json]`` and return the parsed contract.

    Always returns a dict. On a tool error (exit 2) the CLI now emits a
    structured ``{verdict: "error", error: {...}}`` envelope, which we pass
    through unchanged — the caller never has to parse a string. A non-JSON or
    missing-binary failure is itself wrapped in that same envelope. `want_format`
    is False for the few commands (list-json) that always emit JSON and reject
    the flag.
    '''
    cmd = [CVS_BIN, *command_args] + (['--format', 'json'] if want_format else [])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return _error_envelope(f'failed to run {CVS_BIN!r}: {exc}')
    out = proc.stdout.strip()
    if not out:
        return _error_envelope(proc.stderr.strip() or f'cvs exited {proc.returncode} with no output')
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return _error_envelope(f'non-JSON output from cvs: {out[:200]}')


def _error_envelope(message):
    return {'mode': 'error', 'schema_version': 1, 'verdict': 'error', 'error': {'message': message, 'hint': None}}


# --- typed tools (plain functions; thin MCP wrappers in main) ----------------


def describe(command=None, brief=False):
    '''Machine catalog of the CLI. `brief` = names+summaries only; `command` drills in.'''
    args = ['describe']
    if brief:
        args.append('--brief')
    if command:
        args += ['--command', command]
    return cvs_json(args)


def list_suites(suite=None):
    '''List runnable test suites, or the selectable cases within one `suite`.'''
    # list-json always emits JSON and has no --format flag.
    return cvs_json(['list-json', suite] if suite else ['list-json'], want_format=False)


def validate(command, cluster_file, config_file=None):
    '''Offline check of input JSON against a command's declared contract.'''
    args = ['validate', '--command', command, '--cluster_file', cluster_file]
    if config_file:
        args += ['--config_file', config_file]
    return cvs_json(args)


def preflight(cluster_file, config_file=None, nodes=None):
    '''Read-only cluster sanity gate (SSH/ROCm/GPUs/firewall/RDMA).'''
    args = ['preflight', '--cluster_file', cluster_file]
    if config_file:
        args += ['--config_file', config_file]
    if nodes:
        args += ['--nodes', nodes]
    return cvs_json(args)


def run_test(suite, cluster_file, config_file, case=None):
    '''Run a NAMED suite (optionally a specific `case` id) and return JSON results.'''
    args = ['run-json', suite]
    if case:
        args.append(case)
    args += ['--cluster_file', cluster_file, '--config_file', config_file]
    return cvs_json(args)


def results(result_file, config=None):
    '''Summarize one rccl run (busBw per collective/size, optionally vs thresholds).'''
    args = ['results', result_file]
    if config:
        args += ['--config', config]
    return cvs_json(args)


def compare(mode, files, against=None):
    '''Compare rccl results: mode is peers|baseline|scaling; `files` is a list.'''
    args = ['compare', mode, *files]
    if against:
        args += ['--against', against]
    return cvs_json(args)


def main():
    '''Register the typed tools with an MCP server over stdio (needs the `mcp` SDK).'''
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only at runtime
        raise SystemExit(
            "the 'mcp' package is required to run the server: pip install mcp\n"
            '(the typed tools in this module are importable/testable without it)'
        ) from exc

    server = FastMCP('cvs')
    for name in TOOLS:
        server.tool(name=name)(globals()[name])
    server.run()


if __name__ == '__main__':  # pragma: no cover
    main()
