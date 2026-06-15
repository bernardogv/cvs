import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from cvs.cli_plugins.validate_plugin import ValidatePlugin


class TestValidatePlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plugin = ValidatePlugin()
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

    def test_valid_cluster_file_exits_0(self):
        good = self._write('cluster.json', {'node_dict': {'10.0.0.1': {}}, 'username': 'amd'})
        code, out, _ = self._run(['validate', '--command', 'preflight', '--cluster_file', good, '--format', 'json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['verdict'], 'pass')

    def test_bad_cluster_file_exits_1(self):
        bad = self._write('cluster.json', {'username': 'amd'})  # no node_dict
        code, out, _ = self._run(['validate', '--command', 'preflight', '--cluster_file', bad, '--format', 'json'])
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(report['verdict'], 'fail')
        self.assertIn('node_dict', ' '.join(f['issue'] for f in report['findings']))

    def test_unknown_command_exits_2(self):
        good = self._write('cluster.json', {'node_dict': {}})
        code, _, err = self._run(['validate', '--command', 'bogus', '--cluster_file', good])
        self.assertEqual(code, 2)
        self.assertIn('bogus', err)

    def test_command_without_input_contract_passes_trivially(self):
        # 'list' declares no input_files; validating it is a no-op pass.
        code, out, _ = self._run(['validate', '--command', 'list', '--format', 'json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['verdict'], 'pass')

    def test_table_format_renders(self):
        bad = self._write('cluster.json', {'username': 'amd'})
        code, out, _ = self._run(['validate', '--command', 'preflight', '--cluster_file', bad])
        self.assertEqual(code, 1)
        self.assertIn('node_dict', out)


if __name__ == '__main__':
    unittest.main()
