'''
cvs results — clean summary of a single rccl run's aggregated results: bus
bandwidth per collective x message size, optionally graded against the config's
expected thresholds. Pretty table for humans, JSON for agents, CSV for
spreadsheets. Exit codes: 0 pass/info, 1 below expected, 2 usage/tool error.
'''

import json
import sys
from pathlib import Path

import cvs.lib.compare_lib as compare_lib
import cvs.lib.results_lib as results_lib
import cvs.lib.validation_report as validation_report

from .base import SubcommandPlugin


class ResultsPlugin(SubcommandPlugin):
    def get_name(self):
        return 'results'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('results', help='Summarize a single rccl run (busBw per collective/size)')
        parser.set_defaults(_plugin=self)
        parser.add_argument('result_file', help='aggregated rccl result JSON')
        parser.add_argument('--config', default=None, help='config JSON; enables actual-vs-expected pass/fail')
        parser.add_argument('--format', choices=validation_report.FORMATS, default='table')
        return parser

    def describe(self):
        return {
            'summary': 'Summarize one rccl run: busBw per collective/size, optionally vs config thresholds.',
            'read_only': True,
            'exit_codes': {'0': 'pass or info', '1': 'below expected threshold', '2': 'usage or tool error'},
            'input_files': [
                {'arg': 'result_file', 'format': 'json', 'required_keys': [], 'optional_keys': []},
                {'arg': '--config', 'format': 'json', 'required_keys': [], 'optional_keys': ['rccl']},
            ],
            'examples': [
                'cvs results run.json --format table',
                'cvs results run.json --config config.json --format json',
            ],
            'output': {
                'envelope': 'response_contract',
                'finding_keys': ['collective', 'size', 'busBw_GB_s', 'expected', 'status'],
            },
        }

    def run(self, args):
        try:
            report = self._build_report(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            validation_report.emit_error(str(exc), args.format)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    def _build_report(self, args):
        rows = compare_lib.load_aggregated_rows(args.result_file)
        expected = None
        if args.config:
            config = json.loads(Path(args.config).read_text())
            expected = results_lib.thresholds_from_config(config)
        return results_lib.build_results_report(rows, expected)
