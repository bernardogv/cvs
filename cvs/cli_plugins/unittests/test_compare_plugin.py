import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import cvs.lib.compare_lib as compare_lib
from cvs.cli_plugins.compare_plugin import ComparePlugin
from cvs.lib.unittests.fixtures.gen_rccl_fixtures import make_rows


class TestComparePlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plugin = ComparePlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _write(self, name, rows):
        p = Path(self.tmp.name) / f'{name}.json'
        p.write_text(json.dumps(rows))
        return str(p)

    def _run(self, argv):
        args = self.parser.parse_args(argv)
        with self.assertRaises(SystemExit) as ctx:
            self.plugin.run(args)
        return ctx.exception.code

    def test_peers_pass_exits_0(self):
        files = [self._write(f'node{i}', make_rows()) for i in range(1, 4)]
        self.assertEqual(self._run(['compare', 'peers', *files]), 0)

    def test_peers_fail_exits_1(self):
        files = [self._write(f'node{i}', make_rows()) for i in range(1, 3)]
        files.append(self._write('node3', make_rows(scale=0.85)))
        self.assertEqual(self._run(['compare', 'peers', *files]), 1)

    def test_peers_bad_file_exits_2(self):
        bad = Path(self.tmp.name) / 'bad.json'
        bad.write_text('{}')
        self.assertEqual(self._run(['compare', 'peers', str(bad)]), 2)

    def test_baseline_regression_exits_1(self):
        baseline = compare_lib.make_baseline(compare_lib._rows_to_map(make_rows()), meta={'name': 'good'})
        compare_lib.save_baseline(baseline, 'good', store_dir=self.tmp.name)
        current = self._write('current', make_rows(scale=0.85))
        code = self._run(['compare', 'baseline', current, '--against', 'good', '--store', self.tmp.name])
        self.assertEqual(code, 1)

    def test_scaling_pass_exits_0(self):
        r2 = self._write('r2', make_rows(nodes=2))
        r4 = self._write('r4', make_rows(nodes=4))
        self.assertEqual(self._run(['compare', 'scaling', r2, r4]), 0)

    def test_json_format_prints_valid_json(self):
        files = [self._write(f'node{i}', make_rows()) for i in range(1, 4)]
        args = self.parser.parse_args(['compare', 'peers', *files, '--format', 'json'])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            self.plugin.run(args)
        self.assertEqual(json.loads(buf.getvalue())['mode'], 'peers')


if __name__ == '__main__':
    unittest.main()
