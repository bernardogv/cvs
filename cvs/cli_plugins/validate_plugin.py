'''
cvs validate — offline check of cluster/config JSON inputs against a command's
declared contract, before any long run. Reuses the `cvs describe` contract as
the single source of truth for required keys.
Exit codes: 0 pass, 1 validation failure, 2 usage/tool error.
'''

import sys

import cvs.lib.input_validation_lib as input_validation_lib
import cvs.lib.validation_report as validation_report

from . import describe_plugin
from .base import SubcommandPlugin

# Input-file flags validate knows how to accept and read. Maps a contract
# arg -> the argparse attribute holding its path.
_FILE_ARGS = {'--cluster_file': 'cluster_file', '--config_file': 'config_file'}


class ValidatePlugin(SubcommandPlugin):
    def get_name(self):
        return 'validate'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser(
            'validate', help='Validate cluster/config JSON inputs for a command (offline, no cluster)'
        )
        parser.set_defaults(_plugin=self)
        parser.add_argument('--command', required=True, help='Command whose input contract to validate against')
        parser.add_argument('--cluster_file', default=None)
        parser.add_argument('--config_file', default=None)
        parser.add_argument('--format', choices=validation_report.FORMATS, default='table')
        return parser

    def describe(self):
        return {
            'summary': 'Offline validation of cluster/config JSON against a command\'s declared input contract.',
            'read_only': True,
            'exit_codes': {'0': 'pass', '1': 'validation failure', '2': 'usage or tool error'},
            'examples': [
                'cvs validate --command preflight --cluster_file cluster.json --format json',
            ],
            'output': {
                'envelope': 'response_contract',
                'finding_keys': ['file', 'arg', 'issue'],
            },
        }

    def run(self, args):
        try:
            report = self._validate(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            validation_report.emit_error(str(exc), args.format)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    def _validate(self, args):
        contracts = _input_contracts(args.command)
        provided = {arg: getattr(args, attr, None) for arg, attr in _FILE_ARGS.items()}
        return input_validation_lib.validate_inputs(contracts, provided)


def _input_contracts(command_name):
    '''The `input_files` contract for *command_name*, via the describe catalog.

    Raises ValueError (-> exit 2) for an unknown command, so an agent gets the
    same "unknown command" failure mode as `cvs describe --command`.
    '''
    catalog = describe_plugin.build_catalog()
    for cmd in catalog['commands']:
        if cmd['name'] == command_name:
            return cmd.get('input_files', [])
    raise ValueError(f'unknown command {command_name!r}; run "cvs describe" to list commands')
