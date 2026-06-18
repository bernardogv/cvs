# CLAUDE.md — agent-operable CVS

This is a downstream fork of [ROCm/cvs](https://github.com/ROCm/cvs) reworked so an
**AI agent can drive cluster validation end to end**. Every agent command emits a
stable JSON contract (`--format json`) and uses consistent exit codes
(0 pass · 1 validation failure · 2 usage/tool error). Drive the CLI and parse the
JSON — never scrape human text.

## Skills (load these)

- **`cvs-operate`** — the playbook for *operating* CVS to validate a cluster.
  When asked to validate/run against a cluster, load it and follow its **Guided
  operation — first-contact flow**: establish the head node, confirm cvs is
  installed there (install with permission), find or build the cluster file,
  preflight reachability, then guide the user to their goal. Discover over SSH;
  only ask for what you can't see (head node, node credentials, the goal).
- **`cvs-dev`** — background for *developing* in this fork (file map, test/lint
  commands, fork/upstream sync rules). Use it when changing the engine code.

## The operating loop

```
set up     cvs generate cluster_json --hosts 10.0.0.1-8 --username amd \
               --key_file ~/.ssh/id_rsa --output_json_file cluster.json
           cvs copy-config rccl/rccl_config.json --output config.json
           cvs schema cluster_file            # JSON Schema for the inputs
discover   cvs describe --format json         # every command + its contract
           cvs list-json                       # every runnable test suite
validate   cvs validate --command preflight --cluster_file cluster.json --format json
preflight  cvs preflight --cluster_file cluster.json --format json   # +--nodes a,b
run        cvs run-json <suite> --cluster_file cluster.json --config_file config.json --format json
compare    cvs compare peers node*.json --format json
ad-hoc     cvs exec-json --cmd "<shell>" --cluster_file cluster.json --format json  # +--nodes a,b
```

Always run `cvs describe` first to learn the surface; never hard-code commands or
flags. Validate inputs and preflight the cluster before any long run — both fail
fast and read-only.

**Where `cvs` runs:** it must execute where it can SSH to every cluster node —
normally the **head node**, not a laptop. If you're driving from a laptop, run
each command on the head node over SSH (`ssh <headnode> 'cvs ... --format json'`)
and parse the JSON that returns; the input/result files live on the head node.
See the `cvs-operate` skill's "execution location" section.

## Install / run / test

```bash
make install                       # build + install cvs into .cvs_venv
source .cvs_venv/bin/activate       # now `cvs ...` works

# Unit tests: the package conftest makes --cluster_file/--config_file globally
# required and imports pytest_html, so run via .cvs_venv with dummy paths:
.cvs_venv/bin/python -m pytest cvs/lib/unittests/ cvs/cli_plugins/unittests/ -q \
    --cluster_file=/dev/null --config_file=/dev/null

make lint    # ruff + pylint (repo-pinned toolchain)
make fmt     # ruff formatter
```

## Repo conventions (this fork)

- New functionality goes in **new files** (keeps `git rebase upstream/main`
  conflict-free). A PreToolUse hook reminds you when you touch an upstream file.
- Files stay under 500 lines; write the unittest first (a PostToolUse hook runs
  the matching test and ruff after each edit).
- `origin` = this fork, `upstream` = ROCm/cvs (fetch only). Stay current with
  `git fetch upstream && git rebase upstream/main`.
