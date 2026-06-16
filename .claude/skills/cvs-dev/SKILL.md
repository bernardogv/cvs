---
name: cvs-dev
description: Background knowledge for working in this ROCm/cvs fork — test/lint commands, engine-layer file map, fixture conventions, and upstream-PR rules for the cluster-validation work.
user-invocable: false
---

# Working in the CVS fork (cluster-validation engine layer)

This repo is a fork of [ROCm/cvs](https://github.com/ROCm/cvs). We are adding the
agent-driven cluster-validation engine. Full design:
`~/Projects/amd/cluster-validation-plugin/docs/superpowers/specs/2026-06-10-agent-cluster-validation-design.md`

## Hard rules

- **New functionality goes in NEW files.** Touch existing upstream files only for
  unavoidable registration glue, with minimal diffs (a PreToolUse hook reminds you).
- **Files under 500 lines** (a PostToolUse hook enforces this).
- **TDD**: write the unittest first; the PostToolUse hook auto-runs the matching
  test file after every lib/plugin edit.
- Exit codes for new CLI commands: 0 = pass, 1 = validation failure, 2 = tool/usage error.
- `--format json` output is a **stable contract** consumed by the MCP layer in
  `~/Projects/amd/cluster-validation-plugin`. Schema changes require updating the
  contract tests there in the same change.

## Our files (engine layer)

| File | Tests |
|------|-------|
| `cvs/lib/compare_lib.py` | `cvs/lib/unittests/test_compare_lib.py` |
| `cvs/lib/preflight_lib.py` | `cvs/lib/unittests/test_preflight_lib.py` |
| `cvs/cli_plugins/preflight_plugin.py` | `cvs/cli_plugins/unittests/test_preflight_plugin.py` |
| `cvs/cli_plugins/baseline_plugin.py` | `cvs/cli_plugins/unittests/test_baseline_plugin.py` |
| `cvs/cli_plugins/compare_plugin.py` | `cvs/cli_plugins/unittests/test_compare_plugin.py` |
| `cvs/cli_plugins/describe_plugin.py` | `cvs/cli_plugins/unittests/test_describe_plugin.py` |
| `cvs/cli_plugins/validate_plugin.py` | `cvs/cli_plugins/unittests/test_validate_plugin.py` |
| `cvs/cli_plugins/run_json_plugin.py` | `cvs/cli_plugins/unittests/test_run_json_plugin.py` |
| `cvs/cli_plugins/exec_json_plugin.py` | `cvs/cli_plugins/unittests/test_exec_json_plugin.py` |
| `cvs/cli_plugins/list_json_plugin.py` | `cvs/cli_plugins/unittests/test_list_json_plugin.py` |
| `cvs/cli_plugins/schema_plugin.py` | `cvs/cli_plugins/unittests/test_schema_plugin.py` |
| `cvs/cli_plugins/results_plugin.py` | `cvs/cli_plugins/unittests/test_results_plugin.py` |
| `cvs/lib/input_validation_lib.py` | `cvs/lib/unittests/test_input_validation_lib.py` |
| `cvs/lib/results_lib.py` | `cvs/lib/unittests/test_results_lib.py` |
| `cvs/lib/input_schema_lib.py` | `cvs/lib/unittests/test_input_schema_lib.py` |
| `cvs/lib/junit_report_lib.py` | `cvs/lib/unittests/test_junit_report_lib.py` |
| `cvs/lib/node_select_lib.py` | `cvs/lib/unittests/test_node_select_lib.py` |
| `cvs/lib/remote_exec_lib.py` | `cvs/lib/unittests/test_remote_exec_lib.py` |

`describe_plugin.py` is the **agent discovery keystone**: `cvs describe --format json`
returns a machine-readable catalog of every subcommand (args auto-derived from
argparse + optional per-command semantics from each plugin's `describe()`). An
agent calls it first to learn the whole CLI surface. To make a new command rich
in the catalog, give its plugin a `describe()` returning
`summary`/`read_only`/`exit_codes`/`input_files`/`examples` (see
`base.py::SubcommandPlugin.describe`); commands without it still get a full arg
listing for free.

## Adding a new agent command (checklist)

Follow the established pattern so the surface stays consistent (see any of
preflight/validate/results for a template):

1. **Tests first (TDD).** Write `test_<name>_lib.py` and/or
   `test_<name>_plugin.py` before the code. The PostToolUse hook auto-runs the
   matching test after each edit.
2. **Pure logic in a new lib** `cvs/lib/<name>_lib.py` (validated input, returns
   a report dict). **CLI in a new plugin** `cvs/cli_plugins/<name>_plugin.py`
   subclassing `SubcommandPlugin`. New files only — never grow an upstream file.
3. **Output contract.** Result-bearing commands build a report dict and render
   via `validation_report.render(report, fmt)` (table/csv/json); discovery
   commands emit `json.dumps`. Reuse `validation_report.FORMATS` for `--format`.
4. **Exit codes:** `0` pass/ok, `1` validation failure, `2` usage/tool error.
   Wrap input parsing in `try/except (ValueError, FileNotFoundError, OSError)` →
   stderr + `sys.exit(2)`.
5. **`describe()` metadata** on the plugin (summary, read_only, exit_codes,
   input_files, examples) so it shows richly in `cvs describe`.
6. **Validate inputs** so a wrong file errors (exit 2) instead of producing
   misleading output — never fabricate. Reuse existing loaders
   (`compare_lib.load_aggregated_rows`, etc.) where they fit.
7. **Update docs in the same change:** add the file pair to the table above, and
   add the command to the `cvs-operate` skill (loop + command reference).
8. **Reinstall** so the console script sees it: `.cvs_venv/bin/pip install -q -e .`
9. Files stay under 500 lines; run the suite + `make lint` before committing.

## Commands

```bash
# Unit tests. The package conftest makes --cluster_file/--config_file globally
# REQUIRED and imports pytest_html, so run via .cvs_venv with dummy paths:
.cvs_venv/bin/python -m pytest cvs/lib/unittests/ cvs/cli_plugins/unittests/ -q \
    --cluster_file=/dev/null --config_file=/dev/null
# (Plain `python -m pytest ...` fails: missing pytest_html + missing required args.)

# lint/format with the repo-pinned toolchain (creates .ruff_venv on first run)
make lint    # or: .ruff_venv/bin/ruff check cvs/
make fmt     # or: .ruff_venv/bin/ruff format cvs/   (fmt-check to verify only)

# After adding/renaming a CLI plugin, reinstall so the `cvs` console-script sees it:
.cvs_venv/bin/pip install -q -e .
```

Check the `Makefile` for the authoritative target names before assuming `lint`/`format`.

## Fixture conventions

Synthetic rccl-tests result JSONs live next to the unittests under
`cvs/lib/unittests/fixtures/`. Canonical scenarios: healthy fleet, one slow node,
regressed-vs-baseline, sagging scaling curve. Generate them with the fixture
generator (built as part of the engine plan) rather than hand-writing JSON.

## Fork model & upstream sync

This is a **downstream product fork**: `origin` = `github.com/bernardogv/cvs`
(our agent-operable CVS), `upstream` = `github.com/ROCm/cvs` (AMD's). The
`.claude/` agent tooling and the `cvs-operate` skill are **committed** so the
agent-friendly experience ships with the repo. Personal overrides go in
`.claude/settings.local.json`, which is gitignored.

- Keep new functionality in NEW files (still enforced by the PreToolUse hook).
  It is not about PR-reviewability anymore — it keeps `git rebase upstream/main`
  conflict-free when we pull AMD's changes.
- Stay current with AMD: `git fetch upstream && git rebase upstream/main`, then
  `git push --force-with-lease origin <branch>`.
- Commits are still grouped one-logical-unit-per-commit so history stays legible
  and a slice can be cherry-picked upstream later if AMD ever wants it.
