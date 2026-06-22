'''
cvs list-json — machine-readable catalog of test suites so an agent can
enumerate what to run and feed a suite name straight to `cvs run-json`. The
JSON complement to `cvs list` (human table). Reuses ListPlugin's test
discovery.

With a suite argument (`cvs list-json <suite>`) it drills in and lists the
suite's individual, selectable test cases — including parametrized ids like
`test_rccl_perf[all_reduce_perf]`, which are exactly what you pass to
`cvs run-json <suite> "<id>"` to run one specific case. Exit codes: 0 ok,
2 usage/tool error.
'''

import contextlib
import json
import re
import sys
from io import StringIO

import pytest

import cvs.lib.validation_report as validation_report

from .list_plugin import ListPlugin

SCHEMA_VERSION = 1

# pytest --collect-only -q line, e.g. cvs/tests/rccl/rccl_perf.py::test_rccl_perf[all_reduce_perf]
_CASE_RE = re.compile(r'.+\.py::(?P<func>test_[^\[]+)(?P<params>\[.+\])?$')


def build_test_catalog(test_map):
    '''Turn ListPlugin's ``{pkg: {suite: module_path}}`` into the catalog dict.

    Returns ``{schema_version, packages, total}`` where each package is
    ``{package, suites:[{suite, module, group}]}``. ``suite`` is the name to
    pass to ``cvs run-json``; ``group`` is the parent module (test category).
    '''
    packages = []
    total = 0
    for pkg in sorted(test_map):
        suites = []
        for suite in sorted(test_map[pkg]):
            module_path = test_map[pkg][suite]
            group = '.'.join(module_path.split('.')[:-1])
            suites.append({'suite': suite, 'module': module_path, 'group': group})
            total += 1
        packages.append({'package': pkg, 'suites': suites})
    return {'schema_version': SCHEMA_VERSION, 'packages': packages, 'total': total}


def parse_collected_cases(output):
    '''Parse ``pytest --collect-only -q`` *output* into selectable cases.

    Returns a sorted, de-duplicated list of ``{id, function, params}``. ``id`` is
    the pytest node suffix you pass to ``cvs run-json <suite> "<id>"`` (e.g.
    ``test_rccl_perf[all_reduce_perf]``); ``params`` is the parametrize id with
    the brackets stripped, or ``None`` for a plain test.
    '''
    cases = {}
    for line in output.splitlines():
        m = _CASE_RE.match(line.strip())
        if not m:
            continue
        func = m.group('func')
        params = m.group('params')  # '[all_reduce_perf]' or None
        case_id = func + (params or '')
        cases[case_id] = {'id': case_id, 'function': func, 'params': params[1:-1] if params else None}
    return [cases[k] for k in sorted(cases)]


class ListJsonPlugin(ListPlugin):
    def get_name(self):
        return 'list-json'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('list-json', help='Machine-readable test catalog (suites for run-json)')
        parser.set_defaults(_plugin=self)
        parser.add_argument('suite', nargs='?', default=None, help='Drill into a suite: list its selectable test cases')
        parser.add_argument('--package', default=None, help='Filter the catalog to a single package')
        return parser

    def describe(self):
        return {
            'summary': 'Machine-readable test catalog for agents; with a suite arg, lists that suite\'s cases.',
            'read_only': True,
            'exit_codes': {'0': 'ok', '2': 'unknown suite/package or usage error'},
            'examples': [
                'cvs list-json',
                'cvs list-json --package cvs',
                'cvs list-json rccl_perf',
            ],
        }

    def run(self, args):
        if args.suite:
            self._emit_suite(args.suite)
        self._emit_catalog(args.package)

    def _emit_catalog(self, package):
        catalog = build_test_catalog(self.test_map)
        if package:
            pkgs = [p for p in catalog['packages'] if p['package'] == package]
            if not pkgs:
                validation_report.emit_error(
                    f'unknown package {package!r}', 'json', hint='run "cvs list-json" to list packages'
                )
            catalog = {**catalog, 'packages': pkgs, 'total': sum(len(p['suites']) for p in pkgs)}
        print(json.dumps(catalog, indent=2))
        sys.exit(0)

    def _emit_suite(self, suite):
        module_path = self._find_test(suite)
        if not module_path:
            validation_report.emit_error(f'unknown suite {suite!r}', 'json', hint='run "cvs list-json" to list suites')
        test_file = self.get_test_file(module_path)
        cases = parse_collected_cases(self._collect_cases(test_file))
        detail = {
            'schema_version': SCHEMA_VERSION,
            'suite': suite,
            'module': module_path,
            'tests': cases,
        }
        print(json.dumps(detail, indent=2))
        sys.exit(0)

    def _collect_cases(self, test_file):
        '''Run pytest collect-only for *test_file* and return its stdout.

        Dummy --cluster_file/--config_file satisfy the package conftest's
        required options; collection imports the module but runs no test.
        '''
        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            pytest.main([test_file, '--collect-only', '-q', '--cluster_file=dummy', '--config_file=dummy'])
        return buf.getvalue()
