'''
cvs exec-json — run a command across all cluster nodes and emit the
machine-readable validation-report contract (per-node reachability, exit code,
output) instead of free-form text. Unlike `cvs exec`, a missing priv_key_file
falls back to ssh-agent rather than hard-failing.
Exit codes: 0 all nodes reachable and exit 0, 1 a node failed/unreachable,
2 usage/tool error.
'''

import json
import logging
import sys
from pathlib import Path

import cvs.lib.node_select_lib as node_select_lib
import cvs.lib.remote_exec_lib as remote_exec_lib
import cvs.lib.validation_report as validation_report
from cvs.lib.parallel_ssh_lib import Pssh

from .base import SubcommandPlugin

log = logging.getLogger(__name__)


class ExecJsonPlugin(SubcommandPlugin):
    def get_name(self):
        return 'exec-json'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser(
            'exec-json', help='Run a command on all nodes, emit machine-readable per-node JSON'
        )
        parser.set_defaults(_plugin=self)
        parser.add_argument('--cmd', required=True, help='Command to execute on all nodes')
        parser.add_argument('--cluster_file', required=True, help='Path to cluster configuration JSON file')
        parser.add_argument('--nodes', default=None, help='comma-separated node subset (default: whole cluster)')
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            action='store_true',
            help='Preview the command and target nodes without executing anything (no SSH)',
        )
        parser.add_argument('--timeout', type=int, default=None, help='Per-command read timeout in seconds')
        parser.add_argument('--format', choices=validation_report.FORMATS, default='json')
        return parser

    def describe(self):
        return {
            'summary': 'Run a command across all cluster nodes; emit per-node reachability/exit/output as JSON.',
            'read_only': False,
            'exit_codes': {'0': 'all nodes ok', '1': 'a node failed or was unreachable', '2': 'usage or tool error'},
            'input_files': [
                {
                    'arg': '--cluster_file',
                    'format': 'json',
                    'required_keys': ['node_dict'],
                    'optional_keys': ['username', 'priv_key_file', 'env_vars'],
                },
            ],
            'examples': [
                'cvs exec-json --cmd "cat /opt/rocm/.info/version" --cluster_file cluster.json --format json',
                'cvs exec-json --cmd "rocm-smi" --cluster_file cluster.json --dry-run   # preview only, no SSH',
            ],
            'output': {
                'envelope': 'response_contract',
                'finding_keys': ['node', 'issue'],
                'extra_keys': ['command', 'nodes'],
                'nodes_item_keys': ['node', 'reachable', 'exit_code', 'output'],
            },
        }

    def run(self, args):
        try:
            report = self._exec(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            validation_report.emit_error(str(exc), args.format)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    def _exec(self, args):
        cluster = json.loads(Path(args.cluster_file).read_text())
        node_dict = cluster.get('node_dict')
        if not node_dict:
            raise ValueError('cluster file missing required "node_dict" key')
        nodes = node_select_lib.select_nodes(list(node_dict.keys()), args.nodes)
        if getattr(args, 'dry_run', False):
            # No SSH, no Pssh: just show what would run, on which nodes.
            return remote_exec_lib.build_dry_run_report(args.cmd, nodes)
        phdl = Pssh(
            log,
            list(nodes),
            user=cluster.get('username'),
            pkey=cluster.get('priv_key_file'),  # None -> ssh-agent fallback
            stop_on_errors=False,
            env_vars=cluster.get('env_vars'),
        )
        raw = phdl.exec(remote_exec_lib.wrap_command(args.cmd), timeout=args.timeout, print_console=False)
        return remote_exec_lib.build_exec_report(args.cmd, raw, getattr(phdl, 'unreachable_hosts', []))
