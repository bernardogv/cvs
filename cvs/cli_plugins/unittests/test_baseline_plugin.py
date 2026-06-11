import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cvs.lib.compare_lib as compare_lib
from cvs.cli_plugins.baseline_plugin import BaselinePlugin
from cvs.lib.unittests.fixtures.gen_rccl_fixtures import make_rows


CLUSTER = {
    'username': 'amd',
    'priv_key_file': '/home/amd/.ssh/id_rsa',
    'node_dict': {'10.0.0.1': {'bmc_ip': 'NA'}, '10.0.0.2': {'bmc_ip': 'NA'}},
    'env_vars': {},
}
CONFIG = {'rccl': {'cvs_params': {'nic_model': 'thor2'}}}


class TestBaselinePlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plugin = BaselinePlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _run(self, argv):
        args = self.parser.parse_args(argv)
        with self.assertRaises(SystemExit) as ctx:
            self.plugin.run(args)
        return ctx.exception.code

    def test_capture_then_list_show_delete(self):
        store_dir = Path(self.tmp.name) / 'store'
        result = Path(self.tmp.name) / 'r.json'
        result.write_text(json.dumps(make_rows(nodes=2)))
        store = ['--store', str(store_dir)]
        self.assertEqual(self._run(['baseline', 'capture', str(result), '--name', 'mi300x-2n', *store]), 0)
        loaded = compare_lib.load_baseline('mi300x-2n', store_dir=str(store_dir))
        self.assertEqual(loaded['meta']['name'], 'mi300x-2n')
        self.assertEqual(loaded['meta']['node_count'], 2)
        self.assertEqual(loaded['meta']['source_result_file'], str(result))
        self.assertEqual(self._run(['baseline', 'list', *store]), 0)
        self.assertEqual(self._run(['baseline', 'show', 'mi300x-2n', *store]), 0)
        self.assertEqual(self._run(['baseline', 'delete', 'mi300x-2n', *store]), 0)
        self.assertEqual(compare_lib.list_baselines(store_dir=str(store_dir)), [])

    def test_capture_without_flags_fills_version_and_none_placeholders(self):
        store_dir = Path(self.tmp.name) / 'store'
        result = Path(self.tmp.name) / 'r.json'
        result.write_text(json.dumps(make_rows()))
        code = self._run(['baseline', 'capture', str(result), '--name', 'plain', '--store', str(store_dir)])
        self.assertEqual(code, 0)
        meta = compare_lib.load_baseline('plain', store_dir=str(store_dir))['meta']
        self.assertIsInstance(meta['cvs_version'], str)
        self.assertTrue(meta['cvs_version'])
        self.assertIsNone(meta['rocm_version'])
        self.assertIsNone(meta['gpus_per_node'])
        self.assertIsNone(meta['nic_model'])

    @mock.patch('cvs.cli_plugins.baseline_plugin.Pssh')
    def test_capture_with_cluster_and_config_fills_meta(self, mock_pssh):
        store_dir = Path(self.tmp.name) / 'store'
        result = Path(self.tmp.name) / 'r.json'
        result.write_text(json.dumps(make_rows(nodes=2)))
        cluster_file = Path(self.tmp.name) / 'cluster.json'
        cluster_file.write_text(json.dumps(CLUSTER))
        config_file = Path(self.tmp.name) / 'config.json'
        config_file.write_text(json.dumps(CONFIG))
        smi = '\n'.join(f'GPU[{i}]\t\t: card series' for i in range(8))

        def fake_exec(cmd, **kwargs):
            if 'rocm-smi' in cmd:
                return {'10.0.0.1': smi}
            return {'10.0.0.1': '6.4.1-30\n'}

        mock_pssh.return_value.exec.side_effect = fake_exec
        code = self._run(
            [
                'baseline',
                'capture',
                str(result),
                '--name',
                'meta-bl',
                '--store',
                str(store_dir),
                '--cluster_file',
                str(cluster_file),
                '--config_file',
                str(config_file),
            ]
        )
        self.assertEqual(code, 0)
        meta = compare_lib.load_baseline('meta-bl', store_dir=str(store_dir))['meta']
        self.assertEqual(meta['rocm_version'], '6.4.1-30')
        self.assertEqual(meta['gpus_per_node'], 8)
        self.assertEqual(meta['nic_model'], 'thor2')
        self.assertTrue(meta['cvs_version'])
        self.assertEqual(meta['node_count'], 2)
        pssh_args, pssh_kwargs = mock_pssh.call_args
        self.assertEqual(pssh_args[1], ['10.0.0.1'])  # head node only
        self.assertEqual(pssh_kwargs.get('user'), 'amd')
        self.assertEqual(pssh_kwargs.get('pkey'), '/home/amd/.ssh/id_rsa')
        # stop_on_errors=False: record unreachable hosts instead of raising.
        self.assertIs(pssh_kwargs.get('stop_on_errors'), False)

    def test_show_missing_exits_2(self):
        store_dir = Path(self.tmp.name) / 'store'
        self.assertEqual(self._run(['baseline', 'show', 'nope', '--store', str(store_dir)]), 2)

    def test_delete_missing_exits_2(self):
        store_dir = Path(self.tmp.name) / 'store'
        self.assertEqual(self._run(['baseline', 'delete', 'nope', '--store', str(store_dir)]), 2)

    def test_capture_bad_result_exits_2(self):
        store_dir = Path(self.tmp.name) / 'store'
        bad = Path(self.tmp.name) / 'bad.json'
        bad.write_text('{}')
        self.assertEqual(self._run(['baseline', 'capture', str(bad), '--name', 'x', '--store', str(store_dir)]), 2)

    def test_capture_name_with_path_separator_exits_2(self):
        store_dir = Path(self.tmp.name) / 'store'
        result = Path(self.tmp.name) / 'r.json'
        result.write_text(json.dumps(make_rows()))
        code = self._run(['baseline', 'capture', str(result), '--name', 'sub/inner', '--store', str(store_dir)])
        self.assertEqual(code, 2)
        self.assertEqual(compare_lib.list_baselines(store_dir=str(store_dir)), [])


if __name__ == '__main__':
    unittest.main()
