import json
import unittest
from unittest import mock

import cvs.mcp_server as mcp


def _proc(stdout='', stderr='', returncode=0):
    return mock.Mock(stdout=stdout, stderr=stderr, returncode=returncode)


class TestCvsJson(unittest.TestCase):
    def test_parses_json_contract(self):
        report = {'mode': 'preflight', 'verdict': 'pass', 'findings': []}
        with mock.patch('subprocess.run', return_value=_proc(stdout=json.dumps(report))) as run:
            out = mcp.cvs_json(['preflight', '--cluster_file', 'c.json'])
        self.assertEqual(out, report)
        # the server always appends --format json so it gets the contract.
        self.assertIn('--format', run.call_args[0][0])
        self.assertIn('json', run.call_args[0][0])

    def test_passes_structured_error_through(self):
        err = {'mode': 'error', 'verdict': 'error', 'error': {'message': "unknown test 'x'", 'hint': 'use cvs list'}}
        with mock.patch('subprocess.run', return_value=_proc(stdout=json.dumps(err), returncode=2)):
            out = mcp.cvs_json(['run-json', 'x'])
        self.assertEqual(out['verdict'], 'error')  # never a raw string

    def test_missing_binary_wrapped_in_error_envelope(self):
        with mock.patch('subprocess.run', side_effect=FileNotFoundError('no cvs')):
            out = mcp.cvs_json(['describe'])
        self.assertEqual(out['verdict'], 'error')
        self.assertIn('failed to run', out['error']['message'])

    def test_non_json_output_wrapped(self):
        with mock.patch('subprocess.run', return_value=_proc(stdout='Traceback...')):
            out = mcp.cvs_json(['describe'])
        self.assertEqual(out['verdict'], 'error')


class TestTypedTools(unittest.TestCase):
    def _args_for(self, fn, *a, **kw):
        with mock.patch('subprocess.run', return_value=_proc(stdout='{}')) as run:
            fn(*a, **kw)
        return run.call_args[0][0]

    def test_run_test_builds_named_invocation(self):
        argv = self._args_for(mcp.run_test, 'rccl_perf', 'c.json', 'f.json', case='test_rccl_perf[all_reduce_perf]')
        self.assertEqual(argv[:2], [mcp.CVS_BIN, 'run-json'])
        self.assertIn('rccl_perf', argv)
        self.assertIn('test_rccl_perf[all_reduce_perf]', argv)
        self.assertIn('c.json', argv)

    def test_describe_brief_flag(self):
        self.assertIn('--brief', self._args_for(mcp.describe, brief=True))

    def test_preflight_nodes_subset(self):
        argv = self._args_for(mcp.preflight, 'c.json', nodes='node1,node2')
        self.assertIn('--nodes', argv)
        self.assertIn('node1,node2', argv)

    def test_list_suites_omits_format_flag(self):
        # list-json always emits JSON and rejects --format.
        self.assertNotIn('--format', self._args_for(mcp.list_suites))


class TestContainment(unittest.TestCase):
    def test_no_arbitrary_shell_tool_exposed(self):
        # The whole point: an agent on this server can validate + run named
        # suites, but has NO tool to execute free-form commands on the fleet.
        self.assertNotIn('exec', mcp.TOOLS)
        self.assertFalse(any('shell' in t or 'exec' in t for t in mcp.TOOLS))
        # exec_json must not even exist as a callable tool name on the module surface.
        self.assertFalse(hasattr(mcp, 'exec_json'))

    def test_every_advertised_tool_is_callable(self):
        for name in mcp.TOOLS:
            self.assertTrue(callable(getattr(mcp, name)), name)


if __name__ == '__main__':
    unittest.main()
