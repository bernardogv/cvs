'''
cvs preflight — read-only cluster sanity gate (~1 min) before any long run.
Exit codes: 0 pass, 1 checks failed, 2 usage/tool error.
'''

import json
import logging
import sys
from pathlib import Path

import cvs.lib.node_select_lib as node_select_lib
import cvs.lib.preflight_lib as preflight_lib
import cvs.lib.validation_report as validation_report
from cvs.lib.parallel_ssh_lib import Pssh

from .base import SubcommandPlugin

log = logging.getLogger(__name__)


class PreflightPlugin(SubcommandPlugin):
    def get_name(self):
        return 'preflight'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('preflight', help='Validate cluster readiness (SSH/ROCm/binaries/GPUs/firewall)')
        parser.set_defaults(_plugin=self)
        parser.add_argument('--cluster_file', required=True)
        parser.add_argument('--config_file', default=None, help='rccl config JSON (enables binary-path checks)')
        parser.add_argument('--nodes', default=None, help='comma-separated node subset (default: whole cluster)')
        parser.add_argument('--format', choices=validation_report.FORMATS, default='table')
        return parser

    def describe(self):
        return {
            'summary': 'Read-only cluster sanity gate (SSH/ROCm/binaries/GPUs/firewall/RDMA) before any long run.',
            'read_only': True,
            'exit_codes': {'0': 'pass', '1': 'checks failed', '2': 'usage or tool error'},
            'input_files': [
                {
                    'arg': '--cluster_file',
                    'format': 'json',
                    'required_keys': ['node_dict'],
                    'optional_keys': ['username', 'priv_key_file', 'env_vars'],
                },
                {
                    'arg': '--config_file',
                    'format': 'json',
                    'required_keys': [],
                    'optional_keys': ['rccl'],
                },
            ],
            'examples': ['cvs preflight --cluster_file cluster.json --format json'],
        }

    def run(self, args):
        try:
            report = self._preflight(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            validation_report.emit_error(str(exc), args.format)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    def _preflight(self, args):
        cluster = json.loads(Path(args.cluster_file).read_text())
        node_dict = cluster.get('node_dict')
        if not node_dict:
            raise ValueError('cluster file missing required "node_dict" key')
        nodes = node_select_lib.select_nodes(list(node_dict.keys()), args.nodes)
        config = {}
        if args.config_file:
            raw = json.loads(Path(args.config_file).read_text()).get('rccl', {})
            config = {
                'rccl_tests_dir': raw.get('rccl_test_params', {}).get('rccl_tests_dir', ''),
                # No default: preflight_lib skips the mpirun check (with a
                # warning) when mpi_dir is not configured.
                'mpi_dir': raw.get('mpi_params', {}).get('mpi_dir', ''),
                'nic_model': raw.get('cvs_params', {}).get('nic_model'),
            }
        phdl = Pssh(
            log,
            # Copy (defense in depth): Pssh aliases the list it is given and
            # prunes dead hosts from it in place; run_preflight also snapshots.
            list(nodes),
            user=cluster.get('username'),
            pkey=cluster.get('priv_key_file'),  # None -> ssh-agent (later task)
            # Required by preflight_lib: lets Pssh record/prune unreachable
            # hosts on the probe exec instead of raising ConnectionError.
            stop_on_errors=False,
            env_vars=cluster.get('env_vars'),
        )
        return preflight_lib.run_preflight(phdl, nodes, config)
