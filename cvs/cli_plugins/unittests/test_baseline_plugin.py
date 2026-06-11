import argparse
import json
import tempfile
import unittest
from pathlib import Path

import cvs.lib.compare_lib as compare_lib
from cvs.cli_plugins.baseline_plugin import BaselinePlugin
from cvs.lib.unittests.fixtures.gen_rccl_fixtures import make_rows


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
