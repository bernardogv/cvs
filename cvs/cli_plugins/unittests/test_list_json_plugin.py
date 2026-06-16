import argparse
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from cvs.cli_plugins.list_json_plugin import ListJsonPlugin, build_test_catalog, parse_collected_cases


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


COLLECT_OUTPUT = '''\
cvs/tests/rccl/rccl_perf.py::test_print_env_once
cvs/tests/rccl/rccl_perf.py::test_rccl_perf[all_reduce_perf]
cvs/tests/rccl/rccl_perf.py::test_rccl_perf[all_gather_perf]
cvs/tests/rccl/rccl_perf.py::test_rccl_perf[all_reduce_perf]

3 tests collected in 0.4s
'''


class TestParseCollectedCases(unittest.TestCase):
    def test_parses_id_function_and_params(self):
        cases = parse_collected_cases(COLLECT_OUTPUT)
        by_id = {c['id']: c for c in cases}
        self.assertIn('test_rccl_perf[all_reduce_perf]', by_id)
        case = by_id['test_rccl_perf[all_reduce_perf]']
        self.assertEqual(case['function'], 'test_rccl_perf')
        self.assertEqual(case['params'], 'all_reduce_perf')

    def test_non_parametrized_has_null_params(self):
        cases = {c['id']: c for c in parse_collected_cases(COLLECT_OUTPUT)}
        self.assertIsNone(cases['test_print_env_once']['params'])

    def test_dedups_and_sorts(self):
        ids = [c['id'] for c in parse_collected_cases(COLLECT_OUTPUT)]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))  # all_reduce_perf appeared twice

    def test_ignores_noise_lines(self):
        self.assertEqual(parse_collected_cases('3 tests collected\n\nrandom noise'), [])


class TestSuiteDrillIn(unittest.TestCase):
    def setUp(self):
        self.plugin = ListJsonPlugin()
        self.plugin.test_map = TEST_MAP
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

    def test_drills_into_a_suite(self):
        with (
            mock.patch.object(self.plugin, '_collect_cases', return_value=COLLECT_OUTPUT),
            mock.patch.object(self.plugin, 'get_test_file', return_value='/x/agfhc_cvs.py'),
        ):
            code, out, _ = self._run(['list-json', 'agfhc_cvs'])
        self.assertEqual(code, 0)
        detail = json.loads(out)
        self.assertEqual(detail['suite'], 'agfhc_cvs')
        self.assertEqual(detail['module'], 'cvs.tests.health.agfhc_cvs')
        ids = {t['id'] for t in detail['tests']}
        self.assertIn('test_rccl_perf[all_reduce_perf]', ids)

    def test_unknown_suite_exits_2(self):
        code, _, err = self._run(['list-json', 'no_such_suite'])
        self.assertEqual(code, 2)
        self.assertIn('no_such_suite', err)


if __name__ == '__main__':
    unittest.main()
