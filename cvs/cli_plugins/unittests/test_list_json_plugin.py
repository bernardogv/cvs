import argparse
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from cvs.cli_plugins.list_json_plugin import ListJsonPlugin, build_test_catalog


TEST_MAP = {
    'cvs': {
        'agfhc_cvs': 'cvs.tests.health.agfhc_cvs',
        'test_aorta': 'cvs.tests.benchmark.test_aorta',
    },
    'cvs_ext': {
        'extra_test': 'cvs_ext.tests.extra_test',
    },
}


class TestBuildTestCatalog(unittest.TestCase):
    def test_catalog_shape(self):
        catalog = build_test_catalog(TEST_MAP)
        self.assertEqual(catalog['schema_version'], 1)
        self.assertEqual(catalog['total'], 3)
        pkgs = {p['package'] for p in catalog['packages']}
        self.assertEqual(pkgs, {'cvs', 'cvs_ext'})

    def test_suite_carries_module_and_group(self):
        catalog = build_test_catalog(TEST_MAP)
        cvs_pkg = next(p for p in catalog['packages'] if p['package'] == 'cvs')
        agfhc = next(s for s in cvs_pkg['suites'] if s['suite'] == 'agfhc_cvs')
        self.assertEqual(agfhc['module'], 'cvs.tests.health.agfhc_cvs')
        self.assertEqual(agfhc['group'], 'cvs.tests.health')

    def test_sorted_and_serializable(self):
        catalog = build_test_catalog(TEST_MAP)
        names = [p['package'] for p in catalog['packages']]
        self.assertEqual(names, sorted(names))
        json.loads(json.dumps(catalog))


class TestListJsonPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = ListJsonPlugin()
        self.plugin.test_map = TEST_MAP  # override real-FS discovery for determinism
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

    def test_emits_full_catalog(self):
        code, out, _ = self._run(['list-json'])
        self.assertEqual(code, 0)
        catalog = json.loads(out)
        self.assertEqual(catalog['total'], 3)

    def test_package_filter(self):
        code, out, _ = self._run(['list-json', '--package', 'cvs'])
        self.assertEqual(code, 0)
        catalog = json.loads(out)
        self.assertEqual([p['package'] for p in catalog['packages']], ['cvs'])
        self.assertEqual(catalog['total'], 2)

    def test_unknown_package_exits_2(self):
        code, _, err = self._run(['list-json', '--package', 'nope'])
        self.assertEqual(code, 2)
        self.assertIn('nope', err)


if __name__ == '__main__':
    unittest.main()
