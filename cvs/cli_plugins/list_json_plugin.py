'''
cvs list-json — machine-readable catalog of test suites so an agent can
enumerate what to run and feed a suite name straight to `cvs run-json`. The
JSON complement to `cvs list` (human table). Reuses ListPlugin's test
discovery. Exit codes: 0 ok, 2 usage/tool error.
'''

import json
import sys

from .list_plugin import ListPlugin

SCHEMA_VERSION = 1


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


class ListJsonPlugin(ListPlugin):
    def get_name(self):
        return 'list-json'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('list-json', help='Machine-readable test catalog (suites for run-json)')
        parser.set_defaults(_plugin=self)
        parser.add_argument('--package', default=None, help='Filter to a single package')
        return parser

    def describe(self):
        return {
            'summary': 'Machine-readable catalog of test suites for agents; feed a suite name to run-json.',
            'read_only': True,
            'exit_codes': {'0': 'ok', '2': 'unknown --package or usage error'},
            'examples': ['cvs list-json', 'cvs list-json --package cvs'],
        }

    def run(self, args):
        catalog = build_test_catalog(self.test_map)
        if args.package:
            pkgs = [p for p in catalog['packages'] if p['package'] == args.package]
            if not pkgs:
                print(f'error: unknown package {args.package!r}; run "cvs list-json" to list packages', file=sys.stderr)
                sys.exit(2)
            catalog = {**catalog, 'packages': pkgs, 'total': sum(len(p['suites']) for p in pkgs)}
        print(json.dumps(catalog, indent=2))
        sys.exit(0)
