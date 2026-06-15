---
name: cvs-operate
description: Use when operating (not developing) CVS to validate an AMD cluster — the agent loop for driving the cvs CLI end to end (discover → validate → preflight → run → compare), the stable JSON contract, and exit-code semantics.
user-invocable: true
---

# Operating CVS as an agent

CVS is a cluster-validation CLI. These commands are designed to be driven by an
agent: every one emits a **stable JSON contract** on `--format json` and uses
**consistent exit codes**. Drive them; parse the JSON; never scrape human text.

## Where `cvs` runs (execution location) — check this FIRST

`cvs` must run somewhere with **SSH reachability to every cluster node** — almost
always the **head node**, because the node IPs and `priv_key_file` in
`cluster.json` are only valid from there. Separate two roles:

- **You (the agent / brain)** decide and parse — you may be on a laptop.
- **`cvs` (the hands)** SSHes to the nodes — it runs on the head node.

Before running anything, determine where you are:

- **Already on the head node** (working dir has the installed `cvs`, and `cvs`
  can reach the nodes) → run commands directly, as written below.
- **On a laptop / remote machine** → do **not** run `cvs` locally; it can't reach
  the private compute nodes. Run every command **on the head node over SSH** and
  parse the JSON that comes back (the JSON contract is exactly what makes this
  work across the SSH pipe):

  ```bash
  ssh <headnode> 'cd <cvs_dir> && source .cvs_venv/bin/activate && \
      cvs preflight --cluster_file cluster.json --format json'
  ```

  The input files (`cluster.json`, `config.json`) and any result JSONs live on
  the **head node**, so `generate`/`copy-config`/`validate`/`compare` all run
  there too (paths are head-node paths). Confirm the head-node host alias and the
  cvs directory with the user if you don't know them. If an MCP layer
  (cluster-validation-plugin) is available, prefer its tools — it wraps exactly
  this SSH-to-head-node execution for you.

Every command in this skill is written as `cvs ...`; when driving from a laptop,
wrap it in `ssh <headnode> '... --format json'`.

## The loop

```
0. set up     cvs generate cluster_json --hosts 10.0.0.1-8 --username amd \
                  --key_file ~/.ssh/id_rsa --output_json_file cluster.json
              cvs copy-config rccl/rccl_config.json --output config.json
1. discover   cvs describe --format json          # commands + their contracts
              cvs list-json                         # test suites you can run
2. validate   cvs validate --command <cmd> --cluster_file C [--config_file F] --format json
3. preflight  cvs preflight --cluster_file C [--config_file F] --format json
4. run        cvs run-json <suite> --cluster_file C --config_file F --format json
5. compare    cvs compare peers node*.json --format json
              cvs compare baseline run.json --against <name> --format json
              cvs compare scaling run_2n.json run_4n.json ... --format json

any time:     cvs exec-json --cmd "<shell>" --cluster_file C --format json
target subset: add --nodes 10.0.0.1,10.0.0.3 to preflight / exec-json
```

**Setting up configs (step 0).** Build the cluster file with `cvs generate
cluster_json` (it expands host ranges like `10.0.0.1-8` and `host[1-10]`) and a
test config with `cvs copy-config` from the bundled templates. For the exact
input shape, `cvs schema cluster_file` / `cvs schema config_file` emit a JSON
Schema you can validate against or generate from. Then *always* `cvs validate`
the result before using it — a generated cluster file passes validation
cleanly, so a failure means you edited in a mistake.

**Discovering what to run (step 1).** `cvs describe` lists every *command*;
`cvs list-json` lists every *test suite* (`{suite, module, group}`). Feed a
`suite` name straight to `cvs run-json`. Both are machine-readable — never parse
`cvs list`'s human table.

**Targeting a subset.** `preflight` and `exec-json` take `--nodes a,b,c` to hit
a rack or a suspect node instead of the whole fleet (omit for the whole cluster;
an unknown node is exit 2).

Always run **describe first** (step 1) — it tells you, machine-readably, every
command, its arguments, the required keys of each input file, and what its exit
codes mean. Never hard-code the command surface; read it from `describe`.

Then, before any long-running step, **validate** the inputs (step 2, instant,
offline) and **preflight** the cluster (step 3, ~1 min, read-only). Both fail
fast so you never lose 40 minutes to a typo'd IP or a missing rccl build.

## Exit codes (uniform across the agent commands)

| Code | Meaning |
|------|---------|
| 0 | pass / ok |
| 1 | validation failure (checks ran, something is wrong) |
| 2 | usage or tool error (bad args, unknown command/test, unreadable file) |

Branch on these. `1` means "the cluster/inputs/results are bad" → report and
stop. `2` means "you called it wrong" → fix the invocation and retry.

## JSON report contract

`validate`, `preflight`, `compare`, and `run-json` all emit a report dict with a
common core:

```json
{
  "mode": "validate|preflight|compare|run",
  "schema_version": 1,
  "verdict": "pass|fail",
  "findings": [ { ... } ],   // uniform keys within a report; [] when clean
  "warnings": [ "..." ]
}
```

- `verdict` is the headline. `findings` are the actionable items (each report
  type has its own finding keys — e.g. validate: `{file, arg, issue}`; run-json:
  `{test, outcome, message}`). `run-json` also carries `tests[]` and a
  `summary` count block.
- Treat `schema_version` as a compatibility gate: if it ever bumps, re-read
  `describe` and adapt rather than assuming field positions.

## Agent-friendly command reference

| Command | Purpose | Read-only |
|---------|---------|-----------|
| `cvs describe` | machine catalog of the whole CLI | yes |
| `cvs list-json` | machine catalog of test suites (feed a suite to run-json) | yes |
| `cvs schema` | JSON Schema for cluster_file / config_file | yes |
| `cvs validate` | offline check of cluster/config JSON for a command | yes |
| `cvs preflight` | cluster sanity gate (SSH/ROCm/binaries/GPUs/firewall/RDMA) `--nodes` | yes |
| `cvs run-json` | run a test, emit JSON results (not pytest text/HTML) | no |
| `cvs exec-json` | run a shell command on every node, per-node JSON (reachability/exit/output) | no |
| `cvs compare` | peers / baseline / scaling comparison of rccl results | yes |
| `cvs baseline` | capture/list/show/delete known-good baselines | capture writes |

**Running commands across nodes.** Use `cvs exec-json`, not `cvs exec`: it
returns a `nodes[]` array of `{node, reachable, exit_code, output}` and a
`verdict`, so you can tell exactly which node failed. It also falls back to
ssh-agent when the cluster file has no `priv_key_file` (plain `cvs exec` errors
out). Example — check the ROCm version everywhere and branch on the result:
`cvs exec-json --cmd "cat /opt/rocm/.info/version" --cluster_file cluster.json --format json`.

Inputs (`cluster_file`, `config_file`) can be scaffolded with `cvs generate` and
`cvs copy-config`, then checked with `cvs validate` before use.

## Don't

- Don't parse `--format table` output — it is for humans; use `json`.
- Don't skip `validate`/`preflight` to "save time"; they exist to save time.
- Don't assume a command's flags — get them from `cvs describe`.
