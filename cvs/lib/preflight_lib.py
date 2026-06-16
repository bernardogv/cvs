'''
Read-only cluster preflight: catch the failures that otherwise surface
40 minutes into a run. Operates through an existing Pssh handle
(phdl.exec(cmd) -> {host: output_str}); fully testable with a fake handle.

The Pssh handle MUST be constructed with stop_on_errors=False. Pssh only
records per-host connection failures and prunes them from reachable_hosts
(via _process_output -> prune_unreachable_hosts) in that mode; with the
default stop_on_errors=True the first exec against a dead node raises a
pssh ConnectionError instead. Pruning happens as a side effect of an exec,
so run_preflight issues a trivial probe exec before the reachability check
reads phdl.reachable_hosts.

Report shape follows the compare_lib contract (schema_version 1):
verdict/findings/warnings plus a full per-node 'checks' list.
'''

import re

from cvs.lib.compare_lib import SCHEMA_VERSION

# Per-command cap so one hung node can't stall the whole gate.
EXEC_TIMEOUT_S = 30


def run_preflight(phdl, nodes, config):
    """Run all preflight checks. Returns a report dict (contract v1).

    *phdl* must be a Pssh constructed with stop_on_errors=False
    (see module docstring).
    """
    # Snapshot the caller's list: real Pssh ALIASES host_list as
    # reachable_hosts (parallel_ssh_lib.py:43) and prune_unreachable_hosts
    # .remove()s dead nodes from it in place (:101). Without this copy,
    # pruning during the probe would also delete the node from *nodes* and
    # the reachability check below would never report it.
    nodes = list(nodes)
    checks = []
    warnings = []
    # Probe first: with stop_on_errors=False, an exec is what triggers Pssh's
    # unreachable-host pruning — reachability below reads the pruned list.
    phdl.exec('echo preflight-probe', timeout=EXEC_TIMEOUT_S, print_console=False)
    checks.extend(_check_reachability(phdl, nodes))
    # Policy: an unreachable node gets exactly one finding (reachability);
    # the remaining checks run on live nodes only, with one warning per
    # skipped node instead of a pile of 'no output' noise.
    reachable = set(getattr(phdl, 'reachable_hosts', nodes))
    live = [n for n in nodes if n in reachable]
    warnings.extend(f'node {n} unreachable; remaining checks skipped for it' for n in nodes if n not in reachable)
    checks.extend(
        _check_same_output(
            phdl,
            live,
            'rocm_version',
            'cat /opt/rocm/.info/version',
            hint='Install the same ROCm version on every node.',
        )
    )
    # Trust boundary: config values (rccl_tests_dir, mpi_dir) and node names come
    # from the operator-controlled cluster/config files; they are deliberately
    # interpolated into shell commands run on the operator's own nodes.
    rccl_dir = config.get('rccl_tests_dir')
    if rccl_dir:
        checks.extend(
            _check_ok(
                phdl,
                live,
                'rccl_tests_binary',
                f'test -x {rccl_dir}/all_reduce_perf && echo OK || echo MISSING',
                hint=f'Build rccl-tests on the node ({rccl_dir} missing all_reduce_perf).',
            )
        )
    else:
        warnings.append('rccl_tests_dir not configured; skipping rccl_tests_binary check')
    mpi_dir = config.get('mpi_dir')
    if mpi_dir:
        checks.extend(
            _check_ok(
                phdl,
                live,
                'mpirun',
                f'test -x {mpi_dir}/bin/mpirun && echo OK || echo MISSING',
                hint=f'Install Open MPI or fix mpi_dir ({mpi_dir}/bin/mpirun not found).',
            )
        )
    else:
        warnings.append('mpi_dir not configured; skipping mpirun check')
    checks.extend(_check_gpu_count(phdl, live))
    checks.extend(_check_firewall(phdl, live))
    if config.get('nic_model'):
        checks.extend(_check_rdma(phdl, live))

    findings = [c for c in checks if not c['ok']]
    return {
        'schema_version': SCHEMA_VERSION,
        'mode': 'preflight',
        'verdict': 'fail' if findings else 'pass',
        'findings': findings,
        'warnings': warnings,
        'checks': checks,
        # Original node count: the snapshot above precedes any pruning.
        'nodes': len(nodes),
    }


def _result(node, check, ok, detail, hint=''):
    entry = {'node': node, 'check': check, 'ok': ok, 'detail': detail}
    if not ok:
        entry['hint'] = hint
    return entry


def _check_reachability(phdl, nodes):
    reachable = set(getattr(phdl, 'reachable_hosts', nodes))
    return [
        _result(
            n,
            'reachability',
            n in reachable,
            'reachable' if n in reachable else 'unreachable over SSH',
            hint='Check IP, ssh key/agent, and that sshd is running.',
        )
        for n in nodes
    ]


def _check_same_output(phdl, nodes, check, cmd, hint):
    out = phdl.exec(cmd, timeout=EXEC_TIMEOUT_S, print_console=False)
    values = {n: (out.get(n) or '').strip() for n in nodes}
    distinct = {v for v in values.values() if v}
    consistent = len(distinct) == 1 and all(values.values())
    return [
        _result(
            n,
            check,
            consistent and bool(v),
            v or 'no output',
            hint=f'{hint} (cluster saw: {sorted(distinct) or "nothing"})',
        )
        for n, v in values.items()
    ]


def _check_ok(phdl, nodes, check, cmd, hint):
    out = phdl.exec(cmd, timeout=EXEC_TIMEOUT_S, print_console=False)
    return [
        _result(n, check, (out.get(n) or '').strip() == 'OK', (out.get(n) or 'no output').strip(), hint=hint)
        for n in nodes
    ]


def _check_gpu_count(phdl, nodes):
    out = phdl.exec('rocm-smi --showid 2>/dev/null', timeout=EXEC_TIMEOUT_S, print_console=False)
    results = []
    for n in nodes:
        # Anchor at line start so incidental 'GPU[' substrings elsewhere in the
        # output (warnings, env dumps) don't inflate the count.
        count = len(re.findall(r'^GPU\[', out.get(n) or '', re.MULTILINE))
        results.append(
            _result(
                n,
                'gpu_count',
                count > 0,
                f'{count} GPUs visible',
                hint='rocm-smi sees no GPUs: check driver/amdgpu install and permissions.',
            )
        )
    return results


def _check_firewall(phdl, nodes):
    out = phdl.exec('systemctl is-active ufw 2>/dev/null || true', timeout=EXEC_TIMEOUT_S, print_console=False)
    results = []
    for n in nodes:
        state = (out.get(n) or 'unknown').strip()
        results.append(
            _result(
                n,
                'firewall',
                state != 'active',
                f'ufw: {state}',
                hint='Active ufw blocks MPI/NCCL ports; disable it or open the required ranges.',
            )
        )
    return results


def _check_rdma(phdl, nodes):
    # Note: even when /sys/class/infiniband is absent (ls fails), `wc -l` still
    # runs, prints '0', and exits 0 — no `|| echo 0` fallback is needed.
    out = phdl.exec('ls /sys/class/infiniband 2>/dev/null | wc -l', timeout=EXEC_TIMEOUT_S, print_console=False)
    results = []
    for n in nodes:
        try:
            count = int((out.get(n) or '0').strip())
        except ValueError:
            count = 0
        results.append(
            _result(
                n,
                'rdma_devices',
                count > 0,
                f'{count} RDMA devices',
                hint='No RDMA devices visible; check NIC driver/firmware for the configured nic_model.',
            )
        )
    return results
