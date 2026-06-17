import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from cvs.cli_plugins.exec_json_plugin import ExecJsonPlugin


CLUSTER = {'username': 'amd', 'node_dict': {'10.0.0.1': {}, '10.0.0.2': {}}}
CLUSTER_AGENT = {'username': 'amd', 'node_dict': {'10.0.0.1': {}}}  # no priv_key_file


class TestExecJsonPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plugin = ExecJsonPlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _cluster(self, obj):
        p = Path(self.tmp.name) / 'cluster.json'
        p.write_text(json.dumps(obj))
        return str(p)

    def _run(self, argv, exec_return, unreachable=None):
        args = self.parser.parse_args(argv)
        out, err = io.StringIO(), io.StringIO()
        fake = mock.MagicMock()
        fake.exec.return_value = exec_return
        fake.unreachable_hosts = unreachable or []
        with (
            mock.patch('cvs.cli_plugins.exec_json_plugin.Pssh', return_value=fake) as pssh_cls,
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        return ctx.exception.code, out.getvalue(), err.getvalue(), pssh_cls, fake

    def test_success_exits_0_with_json(self):
        cf = self._cluster({**CLUSTER, 'priv_key_file': '/k'})
        code, out, _, _, _ = self._run(
            ['exec-json', '--cmd', 'hostname', '--cluster_file', cf],
            {'10.0.0.1': 'n1\n__CVS_EXIT__0__', '10.0.0.2': 'n2\n__CVS_EXIT__0__'},
        )
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(len(report['nodes']), 2)

    def test_nodes_filter_restricts_to_subset(self):
        cf = self._cluster({**CLUSTER, 'priv_key_file': '/k'})
        _, _, _, pssh_cls, _ = self._run(
            ['exec-json', '--cmd', 'hostname', '--cluster_file', cf, '--nodes', '10.0.0.2'],
            {'10.0.0.2': 'n2\n__CVS_EXIT__0__'},
        )
        # only the requested node is handed to Pssh
        host_arg = pssh_cls.call_args[0][1]
        self.assertEqual(host_arg, ['10.0.0.2'])

    def test_dry_run_does_not_ssh(self):
        cf = self._cluster({**CLUSTER, 'priv_key_file': '/k'})
        args = self.parser.parse_args(
            ['exec-json', '--cmd', 'rm -rf /data', '--cluster_file', cf, '--dry-run', '--format', 'json']
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch('cvs.cli_plugins.exec_json_plugin.Pssh') as pssh_cls,
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 0)
        pssh_cls.assert_not_called()  # the load-bearing assertion: no SSH happened
        report = json.loads(out.getvalue())
        self.assertTrue(report['dry_run'])
        self.assertEqual(report['command'], 'rm -rf /data')
        self.assertEqual({f['node'] for f in report['findings']}, {'10.0.0.1', '10.0.0.2'})

    def test_unknown_node_exits_2(self):
        cf = self._cluster({**CLUSTER, 'priv_key_file': '/k'})
        args = self.parser.parse_args(['exec-json', '--cmd', 'hostname', '--cluster_file', cf, '--nodes', '10.9.9.9'])
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn('10.9.9.9', err.getvalue())

    def test_nonzero_exit_exits_1(self):
        cf = self._cluster({**CLUSTER, 'priv_key_file': '/k'})
        code, out, _, _, _ = self._run(
            ['exec-json', '--cmd', 'false', '--cluster_file', cf],
            {'10.0.0.1': '\n__CVS_EXIT__1__', '10.0.0.2': '\n__CVS_EXIT__0__'},
        )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['verdict'], 'fail')

    def test_wraps_command_with_sentinel(self):
        cf = self._cluster({**CLUSTER, 'priv_key_file': '/k'})
        _, _, _, _, fake = self._run(
            ['exec-json', '--cmd', 'hostname', '--cluster_file', cf],
            {'10.0.0.1': 'n1\n__CVS_EXIT__0__', '10.0.0.2': 'n2\n__CVS_EXIT__0__'},
        )
        sent_cmd = fake.exec.call_args[0][0]
        self.assertIn('hostname', sent_cmd)
        self.assertIn('__CVS_EXIT__', sent_cmd)

    def test_missing_priv_key_uses_ssh_agent_fallback(self):
        # The win over `cvs exec`: no priv_key_file -> pkey=None -> ssh-agent,
        # instead of a hard error.
        cf = self._cluster(CLUSTER_AGENT)
        _, _, _, pssh_cls, _ = self._run(
            ['exec-json', '--cmd', 'hostname', '--cluster_file', cf],
            {'10.0.0.1': 'n1\n__CVS_EXIT__0__'},
        )
        _, kwargs = pssh_cls.call_args
        self.assertIsNone(kwargs.get('pkey'))
        self.assertIs(kwargs.get('stop_on_errors'), False)

    def test_missing_node_dict_exits_2(self):
        cf = self._cluster({'username': 'amd'})  # no node_dict
        args = self.parser.parse_args(['exec-json', '--cmd', 'hostname', '--cluster_file', cf])
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 2)

    def test_missing_cluster_file_exits_2(self):
        args = self.parser.parse_args(['exec-json', '--cmd', 'hostname', '--cluster_file', '/no/such.json'])
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
