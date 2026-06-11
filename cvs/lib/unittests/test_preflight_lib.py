import logging
import unittest
from unittest import mock

from pssh.exceptions import ConnectionError as PsshConnectionError

import cvs.lib.preflight_lib as preflight_lib
from cvs.lib.parallel_ssh_lib import Pssh


class FakePssh:
    """Mimics a Pssh handle constructed with stop_on_errors=False.

    Real semantics mirrored here: reachable_hosts starts as the full host
    list and is only pruned as a side effect of an exec (the preflight probe
    is that first exec); every command — including the probe — is recorded.
    """

    def __init__(self, responses, reachable=None):
        # responses: {cmd_substring: {host: output}}
        # NB: substring keys must remain pairwise non-overlapping across the
        # check commands, or exec() may match the wrong response.
        self.responses = responses
        self._post_probe_reachable = reachable or []
        # Like real Pssh.__init__: full host list until an exec prunes it.
        self.reachable_hosts = list(NODES)
        self.commands = []
        self.timeouts = []
        self._probed = False

    def exec(self, cmd, timeout=None, print_console=True):
        self.commands.append(cmd)
        self.timeouts.append(timeout)
        if not self._probed:
            # First exec triggers pruning, as in Pssh._process_output.
            self.reachable_hosts = list(self._post_probe_reachable)
            self._probed = True
        for sub, resp in self.responses.items():
            if sub in cmd:
                return resp
        return {h: '' for h in self.reachable_hosts}


NODES = ['10.0.0.1', '10.0.0.2']
HEALTHY = {
    '/opt/rocm/.info/version': {n: '7.1.0-86' for n in NODES},
    'all_reduce_perf': {n: 'OK' for n in NODES},
    'mpirun': {n: 'OK' for n in NODES},
    'rocm-smi --showid': {n: 'GPU[0]\nGPU[1]\nGPU[2]\nGPU[3]' for n in NODES},
    'is-active ufw': {n: 'inactive' for n in NODES},
    'infiniband': {n: '8' for n in NODES},
}
CONFIG = {
    'rccl_tests_dir': '/home/u/rccl-tests/build',
    'mpi_dir': '/home/u/openmpi/bin',
}


class TestRunPreflight(unittest.TestCase):
    def test_healthy_cluster_passes(self):
        phdl = FakePssh(HEALTHY, reachable=NODES)
        report = preflight_lib.run_preflight(phdl, NODES, CONFIG)
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['mode'], 'preflight')
        self.assertEqual(report['findings'], [])
        check_names = {c['check'] for c in report['checks']}
        self.assertEqual(
            check_names,
            {'reachability', 'rocm_version', 'rccl_tests_binary', 'mpirun', 'gpu_count', 'firewall'},
        )

    def test_unreachable_node_fails(self):
        phdl = FakePssh(HEALTHY, reachable=NODES[:1])
        report = preflight_lib.run_preflight(phdl, NODES, CONFIG)
        self.assertEqual(report['verdict'], 'fail')
        # Exactly one finding for the dead node — reachability; the remaining
        # checks skip it (one warning) instead of piling on 'no output' noise.
        dead_findings = [f for f in report['findings'] if f['node'] == NODES[1]]
        self.assertEqual([f['check'] for f in dead_findings], ['reachability'])
        self.assertTrue(any(NODES[1] in w and 'remaining checks skipped' in w for w in report['warnings']))
        self.assertEqual(report['nodes'], 2)  # original node count

    def test_rocm_version_mismatch_fails(self):
        responses = dict(HEALTHY)
        responses['/opt/rocm/.info/version'] = {NODES[0]: '7.1.0-86', NODES[1]: '7.0.2-50'}
        report = preflight_lib.run_preflight(FakePssh(responses, NODES), NODES, CONFIG)
        self.assertEqual(report['verdict'], 'fail')
        f = [f for f in report['findings'] if f['check'] == 'rocm_version'][0]
        self.assertIn('hint', f)

    def test_missing_rccl_binary_fails_with_hint(self):
        responses = dict(HEALTHY)
        responses['all_reduce_perf'] = {NODES[0]: 'OK', NODES[1]: 'MISSING'}
        report = preflight_lib.run_preflight(FakePssh(responses, NODES), NODES, CONFIG)
        self.assertEqual(report['verdict'], 'fail')
        f = [f for f in report['findings'] if f['check'] == 'rccl_tests_binary'][0]
        self.assertEqual(f['node'], NODES[1])
        self.assertIn('rccl-tests', f['hint'])

    def test_active_firewall_fails(self):
        responses = dict(HEALTHY)
        responses['is-active ufw'] = {NODES[0]: 'inactive', NODES[1]: 'active'}
        report = preflight_lib.run_preflight(FakePssh(responses, NODES), NODES, CONFIG)
        self.assertTrue(any(f['check'] == 'firewall' for f in report['findings']))

    def test_probe_exec_precedes_reachability_and_sets_timeouts(self):
        phdl = FakePssh(HEALTHY, reachable=NODES)
        preflight_lib.run_preflight(phdl, NODES, CONFIG)
        self.assertIn('preflight-probe', phdl.commands[0])
        self.assertTrue(phdl.timeouts)
        self.assertTrue(
            all(t == preflight_lib.EXEC_TIMEOUT_S for t in phdl.timeouts),
            f'every exec must pass EXEC_TIMEOUT_S, got {phdl.timeouts}',
        )

    def test_empty_config_skips_binary_checks_with_warnings(self):
        report = preflight_lib.run_preflight(FakePssh(HEALTHY, NODES), NODES, {})
        self.assertEqual(report['verdict'], 'pass')
        names = {c['check'] for c in report['checks']}
        self.assertNotIn('rccl_tests_binary', names)
        self.assertNotIn('mpirun', names)
        self.assertTrue(any('rccl_tests_dir' in w for w in report['warnings']))
        self.assertTrue(any('mpi_dir' in w for w in report['warnings']))

    def test_rdma_check_only_when_nic_model_set(self):
        config = dict(CONFIG, nic_model='thor')
        report = preflight_lib.run_preflight(FakePssh(HEALTHY, NODES), NODES, config)
        self.assertIn('rdma_devices', {c['check'] for c in report['checks']})
        report2 = preflight_lib.run_preflight(FakePssh(HEALTHY, NODES), NODES, CONFIG)
        self.assertNotIn('rdma_devices', {c['check'] for c in report2['checks']})


class TestRunPreflightRealPssh(unittest.TestCase):
    """Integration: drive run_preflight through the REAL Pssh with only
    ParallelSSHClient mocked, reproducing the host-list aliasing —
    Pssh.__init__ aliases the caller's list as reachable_hosts
    (parallel_ssh_lib.py:43) and prune_unreachable_hosts .remove()s dead
    nodes from it in place (:101)."""

    def test_pruned_dead_node_still_yields_reachability_finding(self):
        live, dead = '10.0.0.1', '10.0.0.2'

        def lines_for(cmd):
            if 'rocm-smi' in cmd:
                return ['GPU[0]', 'GPU[1]']
            if '/opt/rocm/.info/version' in cmd:
                return ['7.1.0-86']
            if 'test -x' in cmd:
                return ['OK']
            if 'is-active ufw' in cmd:
                return ['inactive']
            return ['preflight-probe']

        class FakeClient:
            """ParallelSSHClient stand-in: dead host raises pssh ConnectionError."""

            def __init__(self, hosts, **kwargs):
                self.hosts = list(hosts)

            def run_command(self, cmd, **kwargs):
                items = []
                for h in self.hosts:
                    item = mock.Mock()
                    item.host = h
                    if h == dead:
                        item.stdout, item.stderr = iter(()), iter(())
                        item.exception = PsshConnectionError('connect failed')
                    else:
                        item.stdout, item.stderr = iter(lines_for(cmd)), iter(())
                        item.exception = None
                    items.append(item)
                return items

        shared = [live, dead]  # the SAME list object handed to Pssh and run_preflight
        with mock.patch('cvs.lib.parallel_ssh_lib.ParallelSSHClient', FakeClient):
            phdl = Pssh(logging.getLogger(__name__), shared, user='amd', stop_on_errors=False)
            report = preflight_lib.run_preflight(phdl, shared, CONFIG)

        # Real Pssh pruned the aliased caller list in place during the probe...
        self.assertEqual(shared, [live])
        # ...but run_preflight's snapshot still surfaces the dead node:
        finding_keys = {(f['node'], f['check']) for f in report['findings']}
        self.assertIn((dead, 'reachability'), finding_keys)
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['nodes'], 2)  # original count, not post-prune
        # Dead node yields exactly the reachability finding — later checks skip it.
        self.assertEqual([f for f in report['findings'] if f['node'] == dead and f['check'] != 'reachability'], [])
        self.assertTrue(any(dead in w and 'unreachable' in w for w in report['warnings']))
        # The healthy live node contributes no findings.
        self.assertEqual([f for f in report['findings'] if f['node'] == live], [])


if __name__ == '__main__':
    unittest.main()
