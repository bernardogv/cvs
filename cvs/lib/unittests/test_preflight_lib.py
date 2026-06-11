import unittest

import cvs.lib.preflight_lib as preflight_lib


class FakePssh:
    """Mimics Pssh.exec returning {host: output_str}; records commands."""

    def __init__(self, responses, reachable=None):
        # responses: {cmd_substring: {host: output}}
        # NB: substring keys must remain pairwise non-overlapping across the
        # check commands, or exec() may match the wrong response.
        self.responses = responses
        self.reachable_hosts = reachable or []
        self.commands = []

    def exec(self, cmd, timeout=None, print_console=True):
        self.commands.append(cmd)
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
        self.assertTrue(any(f['check'] == 'reachability' for f in report['findings']))

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

    def test_rdma_check_only_when_nic_model_set(self):
        config = dict(CONFIG, nic_model='thor')
        report = preflight_lib.run_preflight(FakePssh(HEALTHY, NODES), NODES, config)
        self.assertIn('rdma_devices', {c['check'] for c in report['checks']})
        report2 = preflight_lib.run_preflight(FakePssh(HEALTHY, NODES), NODES, CONFIG)
        self.assertNotIn('rdma_devices', {c['check'] for c in report2['checks']})


if __name__ == '__main__':
    unittest.main()
