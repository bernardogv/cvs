import unittest

import cvs.lib.remote_exec_lib as rx


class TestWrapCommand(unittest.TestCase):
    def test_wrap_appends_exit_sentinel(self):
        wrapped = rx.wrap_command('rocm-smi')
        self.assertIn('rocm-smi', wrapped)
        self.assertIn(rx.EXIT_SENTINEL, wrapped)
        self.assertIn('$?', wrapped)


class TestBuildExecReport(unittest.TestCase):
    def test_all_success(self):
        raw = {
            '10.0.0.1': 'rocm 6.2\n__CVS_EXIT__0__\n',
            '10.0.0.2': 'rocm 6.2\n__CVS_EXIT__0__\n',
        }
        report = rx.build_exec_report('cat /opt/rocm/.info/version', raw, [])
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['mode'], 'exec')
        self.assertEqual(report['schema_version'], rx.SCHEMA_VERSION)
        self.assertEqual(report['findings'], [])
        nodes = {n['node']: n for n in report['nodes']}
        self.assertTrue(nodes['10.0.0.1']['reachable'])
        self.assertEqual(nodes['10.0.0.1']['exit_code'], 0)
        # the sentinel marker is stripped from the reported output.
        self.assertNotIn('__CVS_EXIT__', nodes['10.0.0.1']['output'])
        self.assertIn('rocm 6.2', nodes['10.0.0.1']['output'])

    def test_nonzero_exit_is_a_finding(self):
        raw = {'10.0.0.1': 'bash: nope: command not found\n__CVS_EXIT__127__\n'}
        report = rx.build_exec_report('nope', raw, [])
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['nodes'][0]['exit_code'], 127)
        self.assertEqual(report['findings'][0], {'node': '10.0.0.1', 'issue': 'exit code 127'})

    def test_unreachable_host_is_a_finding(self):
        raw = {'10.0.0.9': 'connection refused\nABORT: Host Unreachable Error'}
        report = rx.build_exec_report('hostname', raw, ['10.0.0.9'])
        self.assertEqual(report['verdict'], 'fail')
        node = report['nodes'][0]
        self.assertFalse(node['reachable'])
        self.assertIsNone(node['exit_code'])
        self.assertEqual(report['findings'][0]['issue'], 'unreachable')

    def test_missing_sentinel_flags_no_exit_code(self):
        # e.g. command was killed before the echo ran.
        raw = {'10.0.0.1': 'partial output with no marker'}
        report = rx.build_exec_report('sleep 999', raw, [])
        self.assertEqual(report['verdict'], 'fail')
        self.assertIsNone(report['nodes'][0]['exit_code'])
        self.assertIn('no exit code', report['findings'][0]['issue'])

    def test_findings_have_uniform_keys(self):
        raw = {'a': 'x\n__CVS_EXIT__1__', 'b': 'y\nABORT: Host Unreachable Error'}
        report = rx.build_exec_report('c', raw, ['b'])
        self.assertEqual({k for f in report['findings'] for k in f}, {'node', 'issue'})

    def test_nodes_sorted_for_stable_output(self):
        raw = {'10.0.0.3': 'x\n__CVS_EXIT__0__', '10.0.0.1': 'y\n__CVS_EXIT__0__'}
        report = rx.build_exec_report('c', raw, [])
        self.assertEqual([n['node'] for n in report['nodes']], ['10.0.0.1', '10.0.0.3'])


if __name__ == '__main__':
    unittest.main()
