'''
cvs run-json — run a CVS test (pytest wrapper) and emit the result as the
machine-readable validation-report contract instead of pytest text/HTML, so an
agent can parse pass/fail and per-test outcomes.
Exit codes: 0 all passed, 1 one or more failed/errored, 2 usage/tool error.
'''

import os
import sys
import tempfile

import pytest

import cvs.lib.junit_report_lib as junit_report_lib
import cvs.lib.validation_report as validation_report

from .list_plugin import ListPlugin


def _dry_run_report(targets):
    '''Preview report: the pytest targets run-json WOULD execute, nothing run.'''
    return {
        'mode': 'run',
        'schema_version': junit_report_lib.SCHEMA_VERSION,
        'verdict': 'pass',
        'dry_run': True,
        'targets': targets,
        'findings': [{'target': t, 'action': 'would-run'} for t in targets],
        'warnings': [f'dry-run: would run {len(targets)} pytest target(s); nothing was executed'],
    }


class RunJsonPlugin(ListPlugin):
    '''Reuses ListPlugin's test discovery (_find_test/get_test_file), like RunPlugin.'''

    def get_name(self):
        return 'run-json'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('run-json', help='Run a test and emit machine-readable JSON results')
        parser.add_argument('test', help='Name of the test file to run')
        parser.add_argument('function', nargs='*', help='Optional: specific test functions to run')
        parser.add_argument('--cluster_file', required=True, help='Path to cluster configuration JSON file')
        parser.add_argument('--config_file', required=True, help='Path to test configuration JSON file')
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            action='store_true',
            help='Preview the pytest targets without running anything (no SSH, no test execution)',
        )
        parser.add_argument('--format', choices=validation_report.FORMATS, default='json')
        parser.set_defaults(_plugin=self)
        return parser

    def get_epilog(self):
        return """
Run-json Commands:
  cvs run-json agfhc --cluster_file c.json --config_file cfg.json
  cvs run-json agfhc test1 test2 --cluster_file c.json --config_file cfg.json --format table"""

    def describe(self):
        return {
            'summary': 'Run a CVS test via pytest and emit the validation-report JSON contract (parseable results).',
            'read_only': False,
            'exit_codes': {'0': 'all passed', '1': 'one or more failed/errored', '2': 'usage or tool error'},
            'input_files': [
                {'arg': '--cluster_file', 'format': 'json', 'required_keys': ['node_dict'], 'optional_keys': []},
                {'arg': '--config_file', 'format': 'json', 'required_keys': [], 'optional_keys': ['rccl']},
            ],
            'examples': ['cvs run-json agfhc --cluster_file cluster.json --config_file config.json --format json'],
        }

    def run(self, args):
        module_path = self._find_test(args.test)
        if not module_path:
            validation_report.emit_error(
                f"unknown test '{args.test}'", args.format, hint="use 'cvs list' to see available tests"
            )
        test_file = self.get_test_file(module_path)

        if getattr(args, 'dry_run', False):
            report = _dry_run_report(self._targets(test_file, args.function))
        else:
            report = self._run_and_parse(test_file, args.function, args.cluster_file, args.config_file)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    @staticmethod
    def _targets(test_file, functions):
        return [f'{test_file}::{fn}' for fn in functions] if functions else [test_file]

    def _run_and_parse(self, test_file, functions, cluster_file, config_file):
        fd, xml_path = tempfile.mkstemp(prefix='cvs-junit-', suffix='.xml')
        os.close(fd)
        try:
            targets = self._targets(test_file, functions)
            pytest_args = [
                *targets,
                f'--cluster_file={cluster_file}',
                f'--config_file={config_file}',
                f'--junit-xml={xml_path}',
            ]
            pytest.main(pytest_args)
            with open(xml_path) as fh:
                return junit_report_lib.parse_junit_xml(fh.read())
        finally:
            if os.path.exists(xml_path):
                os.remove(xml_path)
