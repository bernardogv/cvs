# Pre-built validation workflows

Load this when the user asks for a multi-suite goal ("qualify this cluster",
"burn-in", "is it ready for training") rather than a single test. Each workflow
chains real suites (names from `cvs list-json`) and **branches on the JSON
`verdict` / exit code** of each step — 0 pass, 1 validation fail, 2 tool error.

Pattern for every step:
```
cvs run-json <suite> --cluster_file C --config_file F --format json
  verdict pass (exit 0) → continue
  verdict fail (exit 1) → load AUTO_HEAL.md, remediate, re-run once, else escalate
  exit 2               → fix the invocation (bad args/suite), don't retry blindly
```

`preflight_checks` is always step 0 and is the gate — never start a suite until
it's green (or the user explicitly excludes the failing nodes via `--nodes`).

## Full cluster qualification
New cluster, post-maintenance, periodic health.
```
1. preflight_checks            → gate (auto-heal on fail, retry once)
2. host_configs_cvs            → report non-compliant nodes
3. agfhc_cvs                   → isolate bad GPUs on fail
4. transferbench_cvs           → flag per-GPU bandwidth issues
5. rccl_perf (all collectives) → on pass: cvs results; on fail: compare baseline
6. summary: nodes tested, pass/fail per suite, nodes needing attention, perf vs baseline
```

## Quick health check
Daily spot-check.
```
1. preflight_checks
2. host_configs_cvs
→ summary: healthy / unhealthy nodes
```

## Network validation
After NIC/RDMA changes.
```
1. preflight_checks            → run in full-mesh mode if available (tests node pairs)
2. ib_perf_bw_test             → IB bandwidth
3. rccl_perf (all_reduce only) → multi-node GPU comms
→ network health report
```

## Pre-training readiness
Before a distributed job.
```
1. preflight_checks
2. host_configs_cvs
3. rccl_perf (all_reduce + all_gather)
4. single-node smoke: jax_llama3_1_70b_single  (JAX target)
                  or  megatron_llama3_1_8b_single  (Megatron target)
→ verdict: ready / not ready for distributed training
```

## GPU burn-in
New install, RMA replacement, hardware qual.
```
1. preflight_checks
2. rvs_cvs                     → GPU enumeration + basic
3. agfhc_cvs                   → full stress (highest level)
4. transferbench_cvs           → all modes
→ per-GPU pass / fail / warning
```

## Inference readiness
Before deploying inference.
```
1. preflight_checks
2. host_configs_cvs
3. single-node smoke: vllm_* or sglang_* matching the target model
→ node ready / not ready for inference
```

**Collective selection reminder** (from SKILL.md): for `rccl_perf` pick
collectives by **case id** (`cvs list-json rccl_perf` → run-json with the id);
for `rccl_regression` set them in the **config**. Editing config collectives has
no effect on `rccl_perf`.

<!-- ponytail: markdown playbook, not code. The agent executes these by chaining
     existing run-json/preflight commands and branching on verdict — no workflow
     engine needed. A real DAG runner is only worth it if these need to run
     unattended with persistence across head-node restarts. -->
