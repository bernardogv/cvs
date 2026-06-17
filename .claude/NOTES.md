# Project notes (agent-operable CVS fork)

Working notes for this downstream fork. Kept in `.claude/` (committed with the
fork's agent tooling), separate from upstream code.

## Upstream-PR candidates (send to ROCm/cvs)

Two fixes merged into this fork's product branch are genuine bugs in AMD's
upstream `cvs/lib/rccl_lib.py`, not fork-specific tooling — worth PRing upstream
(merged here, not yet sent up as of 2026-06-16):

1. **UCX PML/TLS selection** (`determine_mpi_pml_config`): the `ucx` branch
   emitted no `--mca pml ucx` (OMPI 5.0.x then under-selects UCX), and `UCX_TLS`
   was pinned literally even for `auto`/`tcp` (the `tcp` default forces the slow
   TCP path). Fix: explicit `--mca pml ucx` + build the UCX env piecewise (keep
   `UCX_UNIFIED_MODE`/`UCX_NET_DEVICES`, only pin a concrete `UCX_TLS`). Measured
   ~170 -> ~358 GB/s all_reduce on 2x MI300X / Thor RoCE. (fork PR #1)

2. **`mpi_dir` root convention**: the launcher builds `{mpi_dir}/bin/mpirun` and
   UCX detection reads `{mpi_dir}/bin/ompi_info` + `{mpi_dir}/lib/libmpi.so`, so
   `mpi_dir` must be the Open MPI **root**. But preflight probed
   `{mpi_dir}/mpirun`, the sample config used `.../openmpi/bin`, and the launcher
   default was `/usr/local/bin` — all reconciled to root. (fork PR #2)

3. **Shared `build_mpirun_cmd()` helper**: `rccl_perf` and `rccl_regression` had
   two near-duplicate inline `mpirun` builders that had drifted (flag order; the
   regression-only `-x` NCCL overrides). Extracted one helper both call, so the
   MPI envelope can't diverge again; confirmed both now render a byte-identical
   envelope. STILL OPEN (separate from this refactor): the two paths pass the
   `threads_per_gpu` config to *different* rccl-tests flags (`-t` vs `-g`) inside
   their `test_cmd` — harmless at the default (1) but inconsistent; the key is
   also misnamed given the 1-rank-per-GPU launch model. Decide intended meaning
   before fixing.

## Results output scope — RCCL only, on purpose

`cvs results` summarizes **only** the RCCL aggregated format (busBw per
collective/size). It is deliberately NOT extended to other categories
(ibperf/inference/AGFHC/...) because:

- There is no shared metrics structure — `update_test_result()` is pass/fail
  only; each category's numbers are a different shape (rccl busBw, ibperf IB
  bandwidth, inference tokens/s) with their own parsers.
- A confident-looking table of wrong numbers is worse than none. `cvs results`
  validates input (`compare_lib.load_aggregated_rows`) and ERRORS on non-rccl
  data instead of fabricating.

Universal **pass/fail** is already covered for every category by `run-json`.
Before adding a metrics view for a new category, inspect a real result file from
it first and confirm the field mapping — don't guess the schema.
