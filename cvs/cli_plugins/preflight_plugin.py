'''
cvs preflight — read-only cluster sanity gate (~1 min) before any long run.
Exit codes: 0 pass, 1 checks failed, 2 usage/tool error.
'''

import json
import logging
import sys
from pathlib import Path

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
        parser.add_argument('--format', choices=validation_report.FORMATS, default='table')
        return parser

    def run(self, args):
        try:
            report = self._preflight(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(2)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    def _preflight(self, args):
        cluster = json.loads(Path(args.cluster_file).read_text())
        node_dict = cluster.get('node_dict')
        if not node_dict:
            raise ValueError('cluster file missing required "node_dict" key')
        nodes = list(node_dict.keys())
        config = {}
        if args.config_file:
            raw = json.loads(Path(args.config_file).read_text()).get('rccl', {})
            config = {
                'rccl_tests_dir': raw.get('rccl_test_params', {}).get('rccl_tests_dir', ''),
                'mpi_dir': raw.get('mpi_params', {}).get('mpi_dir', '/usr/local/bin'),
                'nic_model': raw.get('cvs_params', {}).get('nic_model'),
            }
        phdl = Pssh(
            log,
            nodes,
            user=cluster.get('username'),
            pkey=cluster.get('priv_key_file'),  # None -> ssh-agent (later task)
            env_vars=cluster.get('env_vars'),
        )
        return preflight_lib.run_preflight(phdl, nodes, config)
