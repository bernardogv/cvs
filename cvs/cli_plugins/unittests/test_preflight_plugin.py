import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cvs.cli_plugins.preflight_plugin import PreflightPlugin


CLUSTER = {
    'username': 'amd',
    'priv_key_file': '/home/amd/.ssh/id_rsa',
    'node_dict': {'10.0.0.1': {'bmc_ip': 'NA'}, '10.0.0.2': {'bmc_ip': 'NA'}},
    'env_vars': {},
}
CONFIG = {'rccl': {'rccl_test_params': {'rccl_tests_dir': '/x'}, 'mpi_params': {'mpi_dir': '/y'}}}


class TestPreflightPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cluster_file = Path(self.tmp.name) / 'cluster.json'
        self.cluster_file.write_text(json.dumps(CLUSTER))
        self.config_file = Path(self.tmp.name) / 'config.json'
        self.config_file.write_text(json.dumps(CONFIG))
        self.plugin = PreflightPlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    @mock.patch('cvs.cli_plugins.preflight_plugin.preflight_lib')
    @mock.patch('cvs.cli_plugins.preflight_plugin.Pssh')
    def test_pass_exits_0_and_builds_pssh_from_cluster_file(self, mock_pssh, mock_lib):
        mock_lib.run_preflight.return_value = {
            'verdict': 'pass',
            'findings': [],
            'warnings': [],
            'checks': [],
            'mode': 'preflight',
            'schema_version': 1,
            'nodes': 2,
        }
        args = self.parser.parse_args(
            ['preflight', '--cluster_file', str(self.cluster_file), '--config_file', str(self.config_file)]
        )
        with self.assertRaises(SystemExit) as ctx:
            self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 0)
        _, kwargs = mock_pssh.call_args
        self.assertEqual(kwargs.get('user'), 'amd')
        self.assertEqual(kwargs.get('pkey'), '/home/amd/.ssh/id_rsa')
        # stop_on_errors=False is load-bearing: Pssh only records/prunes
        # unreachable hosts in that mode instead of raising on first exec.
        self.assertIs(kwargs.get('stop_on_errors'), False)
        nodes_arg = mock_lib.run_preflight.call_args[0][1]
        self.assertEqual(nodes_arg, ['10.0.0.1', '10.0.0.2'])

    @mock.patch('cvs.cli_plugins.preflight_plugin.preflight_lib')
    @mock.patch('cvs.cli_plugins.preflight_plugin.Pssh')
    def test_fail_exits_1(self, mock_pssh, mock_lib):
        mock_lib.run_preflight.return_value = {
            'verdict': 'fail',
            'mode': 'preflight',
            'schema_version': 1,
            'nodes': 2,
            'findings': [
                {'node': '10.0.0.2', 'check': 'firewall', 'ok': False, 'detail': 'ufw: active', 'hint': 'disable ufw'}
            ],
            'warnings': [],
            'checks': [],
        }
        args = self.parser.parse_args(['preflight', '--cluster_file', str(self.cluster_file)])
        with self.assertRaises(SystemExit) as ctx:
            self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_missing_cluster_file_exits_2(self):
        args = self.parser.parse_args(['preflight', '--cluster_file', '/nope.json'])
        with self.assertRaises(SystemExit) as ctx:
            self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 2)

    @mock.patch('cvs.cli_plugins.preflight_plugin.preflight_lib')
    @mock.patch('cvs.cli_plugins.preflight_plugin.Pssh')
    def test_no_priv_key_passes_pkey_none(self, mock_pssh, mock_lib):
        cluster = {k: v for k, v in CLUSTER.items() if k != 'priv_key_file'}
        cf = Path(self.tmp.name) / 'cluster_nokey.json'
        cf.write_text(json.dumps(cluster))
        mock_lib.run_preflight.return_value = {
            'verdict': 'pass',
            'findings': [],
            'warnings': [],
            'checks': [],
            'mode': 'preflight',
            'schema_version': 1,
            'nodes': 2,
        }
        args = self.parser.parse_args(['preflight', '--cluster_file', str(cf)])
        with self.assertRaises(SystemExit):
            self.plugin.run(args)
        _, kwargs = mock_pssh.call_args
        self.assertIsNone(kwargs.get('pkey'))  # ssh-agent fallback

    def test_cluster_file_without_node_dict_exits_2(self):
        import contextlib
        import io

        cf = Path(self.tmp.name) / 'cluster_no_nodes.json'
        cf.write_text(json.dumps({'username': 'amd'}))
        args = self.parser.parse_args(['preflight', '--cluster_file', str(cf)])
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn('node_dict', err.getvalue())


if __name__ == '__main__':
    unittest.main()
