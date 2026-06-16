import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from cvs.cli_plugins.results_plugin import ResultsPlugin


def _row(name, size, mean, std=0.5, nodes=2):
    return {
        'name': name,
        'size': size,
        'type': 'float',
        'inPlace': 1,
        'busBw_mean': mean,
        'busBw_std': std,
        'nodes': nodes,
    }


RESULTS = [_row('all_reduce_perf', 8589934592, 358.2), _row('alltoall_perf', 8589934592, 46.1)]
CONFIG = {'rccl': {'results': {'all_reduce_perf': {'bus_bw': {'8589934592': '330.00'}}}}}


class TestResultsPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plugin = ResultsPlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _write(self, name, obj):
        p = Path(self.tmp.name) / name
        p.write_text(json.dumps(obj))
        return str(p)

    def _run(self, argv):
        args = self.parser.parse_args(argv)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        return ctx.exception.code, out.getvalue(), err.getvalue()

    def test_numbers_only_exits_0(self):
        rf = self._write('r.json', RESULTS)
        code, out, _ = self._run(['results', rf, '--format', 'json'])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['mode'], 'results')
        self.assertEqual(len(report['findings']), 2)

    def test_with_config_passes_exits_0(self):
        rf = self._write('r.json', RESULTS)
        cf = self._write('c.json', CONFIG)
        code, out, _ = self._run(['results', rf, '--config', cf, '--format', 'json'])
        self.assertEqual(code, 0)
        report = json.loads(out)
        ar = next(f for f in report['findings'] if f['collective'] == 'all_reduce_perf')
        self.assertEqual(ar['status'], 'PASS')
        self.assertEqual(ar['expected'], '330.00')

    def test_below_threshold_exits_1(self):
        rf = self._write('r.json', [_row('all_reduce_perf', 8589934592, 300.0)])  # below 330
        cf = self._write('c.json', CONFIG)
        code, out, _ = self._run(['results', rf, '--config', cf, '--format', 'json'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['verdict'], 'fail')

    def test_table_format_renders_numbers(self):
        rf = self._write('r.json', RESULTS)
        code, out, _ = self._run(['results', rf])
        self.assertEqual(code, 0)
        self.assertIn('all_reduce_perf', out)
        self.assertIn('358.2', out)

    def test_bad_result_file_exits_2(self):
        bad = self._write('bad.json', {'not': 'a list'})
        code, _, err = self._run(['results', bad])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
