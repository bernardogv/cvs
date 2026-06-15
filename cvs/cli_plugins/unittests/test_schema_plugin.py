import argparse
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from cvs.cli_plugins.schema_plugin import SchemaPlugin


class TestSchemaPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = SchemaPlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _run(self, argv):
        args = self.parser.parse_args(argv)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        return ctx.exception.code, out.getvalue(), err.getvalue()

    def test_emits_cluster_file_schema(self):
        code, out, _ = self._run(['schema', 'cluster_file'])
        self.assertEqual(code, 0)
        s = json.loads(out)
        self.assertIn('$schema', s)
        self.assertIn('node_dict', s['required'])

    def test_emits_config_file_schema(self):
        code, out, _ = self._run(['schema', 'config_file'])
        self.assertEqual(code, 0)
        self.assertIn('rccl', json.loads(out)['properties'])

    def test_invalid_kind_rejected_by_argparse(self):
        # choices= makes argparse exit 2 on an unknown kind.
        with self.assertRaises(SystemExit) as ctx:
            self.parser.parse_args(['schema', 'bogus'])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
