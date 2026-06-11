'''
Read-only cluster preflight: catch the failures that otherwise surface
40 minutes into a run. Operates through an existing Pssh handle
(phdl.exec(cmd) -> {host: output_str}); fully testable with a fake handle.

Report shape follows the compare_lib contract (schema_version 1):
verdict/findings/warnings plus a full per-node 'checks' list.
'''
from cvs.lib.compare_lib import SCHEMA_VERSION


def run_preflight(phdl, nodes, config):
    """Run all preflight checks. Returns a report dict (contract v1)."""
    checks = []
    checks.extend(_check_reachability(phdl, nodes))
    checks.extend(_check_same_output(
        phdl, nodes, 'rocm_version', 'cat /opt/rocm/.info/version',
        hint='Install the same ROCm version on every node.'))
    rccl_dir = config.get('rccl_tests_dir', '')
    checks.extend(_check_ok(
        phdl, nodes, 'rccl_tests_binary',
        f'test -x {rccl_dir}/all_reduce_perf && echo OK || echo MISSING',
        hint=f'Build rccl-tests on the node ({rccl_dir} missing all_reduce_perf).'))
    mpi_dir = config.get('mpi_dir', '/usr/local/bin')
    checks.extend(_check_ok(
        phdl, nodes, 'mpirun',
        f'test -x {mpi_dir}/mpirun && echo OK || echo MISSING',
        hint=f'Install Open MPI or fix mpi_dir ({mpi_dir}/mpirun not found).'))
    checks.extend(_check_gpu_count(phdl, nodes))
    checks.extend(_check_firewall(phdl, nodes))
    if config.get('nic_model'):
        checks.extend(_check_rdma(phdl, nodes))

    findings = [c for c in checks if not c['ok']]
    return {
        'schema_version': SCHEMA_VERSION,
        'mode': 'preflight',
        'verdict': 'fail' if findings else 'pass',
        'findings': findings,
        'warnings': [],
        'checks': checks,
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
        _result(n, 'reachability', n in reachable,
                'reachable' if n in reachable else 'unreachable over SSH',
                hint='Check IP, ssh key/agent, and that sshd is running.')
        for n in nodes
    ]


def _check_same_output(phdl, nodes, check, cmd, hint):
    out = phdl.exec(cmd, print_console=False)
    values = {n: (out.get(n) or '').strip() for n in nodes}
    distinct = {v for v in values.values() if v}
    consistent = len(distinct) == 1 and all(values.values())
    return [
        _result(n, check, consistent and bool(v), v or 'no output',
                hint=f'{hint} (cluster saw: {sorted(distinct) or "nothing"})')
        for n, v in values.items()
    ]


def _check_ok(phdl, nodes, check, cmd, hint):
    out = phdl.exec(cmd, print_console=False)
    return [
        _result(n, check, (out.get(n) or '').strip() == 'OK',
                (out.get(n) or 'no output').strip(), hint=hint)
        for n in nodes
    ]


def _check_gpu_count(phdl, nodes):
    out = phdl.exec('rocm-smi --showid 2>/dev/null', print_console=False)
    results = []
    for n in nodes:
        count = (out.get(n) or '').count('GPU[')
        results.append(_result(
            n, 'gpu_count', count > 0, f'{count} GPUs visible',
            hint='rocm-smi sees no GPUs: check driver/amdgpu install and permissions.'))
    return results


def _check_firewall(phdl, nodes):
    out = phdl.exec('systemctl is-active ufw 2>/dev/null || true', print_console=False)
    results = []
    for n in nodes:
        state = (out.get(n) or 'unknown').strip()
        results.append(_result(
            n, 'firewall', state != 'active', f'ufw: {state}',
            hint='Active ufw blocks MPI/NCCL ports; disable it or open the required ranges.'))
    return results


def _check_rdma(phdl, nodes):
    out = phdl.exec('ls /sys/class/infiniband 2>/dev/null | wc -l', print_console=False)
    results = []
    for n in nodes:
        try:
            count = int((out.get(n) or '0').strip())
        except ValueError:
            count = 0
        results.append(_result(
            n, 'rdma_devices', count > 0, f'{count} RDMA devices',
            hint='No RDMA devices visible; check NIC driver/firmware for the configured nic_model.'))
    return results
