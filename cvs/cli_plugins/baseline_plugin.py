'''
cvs baseline — capture/list/show/delete stored known-good result fingerprints.
Exit codes: 0 ok, 2 usage/tool error.
'''

import importlib.metadata
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import cvs.lib.compare_lib as compare_lib
from cvs.lib.parallel_ssh_lib import Pssh

from .base import SubcommandPlugin

log = logging.getLogger(__name__)

# Per-command cap so a hung head node can't stall capture (matches preflight_lib).
EXEC_TIMEOUT_S = 30


class BaselinePlugin(SubcommandPlugin):
    def get_name(self):
        return 'baseline'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('baseline', help='Manage known-good result baselines')
        parser.set_defaults(_plugin=self)
        sub = parser.add_subparsers(dest='baseline_cmd', required=True)

        capture = sub.add_parser('capture', help='Store a result file as a named baseline')
        capture.add_argument('result_file')
        capture.add_argument('--name', required=True)
        capture.add_argument('--store', default=None)
        capture.add_argument(
            '--cluster_file', default=None, help='cluster JSON; enables rocm_version/gpus_per_node meta from head node'
        )
        capture.add_argument('--config_file', default=None, help='rccl config JSON; enables nic_model meta')

        for cmd, needs_name, help_text in (
            ('list', False, 'List stored baselines'),
            ('show', True, 'Print a baseline as JSON'),
            ('delete', True, 'Delete a stored baseline'),
        ):
            p = sub.add_parser(cmd, help=help_text)
            if needs_name:
                p.add_argument('name')
            p.add_argument('--store', default=None)
        return parser

    def run(self, args):
        try:
            self._dispatch(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    def _dispatch(self, args):
        if args.baseline_cmd == 'capture':
            name = args.name
            if '/' in name or '\\' in name:
                raise ValueError(f'baseline name {name!r} must not contain path separators')
            rows = compare_lib.load_aggregated_rows(args.result_file)
            results = compare_lib._rows_to_map(rows)
            rocm_version, gpus_per_node = _cluster_facts(args.cluster_file)
            meta = {
                'name': name,
                'captured': datetime.now(timezone.utc).isoformat(),
                'node_count': rows[0].get('nodes') if rows else None,
                'source_result_file': str(args.result_file),
                'cvs_version': _cvs_version(),
                'rocm_version': rocm_version,
                'gpus_per_node': gpus_per_node,
                'nic_model': _nic_model(args.config_file),
            }
            path = compare_lib.save_baseline(compare_lib.make_baseline(results, meta), name, store_dir=args.store)
            print(f'baseline "{name}" saved to {path}')
        elif args.baseline_cmd == 'list':
            for name in compare_lib.list_baselines(store_dir=args.store):
                print(name)
        elif args.baseline_cmd == 'show':
            print(json.dumps(compare_lib.load_baseline(args.name, store_dir=args.store), indent=2))
        elif args.baseline_cmd == 'delete':
            compare_lib.delete_baseline(args.name, store_dir=args.store)
            print(f'baseline "{args.name}" deleted')


def _cvs_version():
    try:
        return importlib.metadata.version('cvs')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def _nic_model(config_file):
    if not config_file:
        return None
    raw = json.loads(Path(config_file).read_text())
    return raw.get('rccl', {}).get('cvs_params', {}).get('nic_model')


def _cluster_facts(cluster_file):
    """(rocm_version, gpus_per_node) read from the cluster head node; (None, None) without a cluster file."""
    if not cluster_file:
        return None, None
    cluster = json.loads(Path(cluster_file).read_text())
    node_dict = cluster.get('node_dict')
    if not node_dict:
        raise ValueError('cluster file missing required "node_dict" key')
    head_node = next(iter(node_dict))
    phdl = Pssh(
        log,
        [head_node],
        user=cluster.get('username'),
        pkey=cluster.get('priv_key_file'),  # None -> ssh-agent
        env_vars=cluster.get('env_vars'),
        # Record (don't raise on) an unreachable head node; meta stays None.
        stop_on_errors=False,
    )
    rocm_out = phdl.exec('cat /opt/rocm/.info/version', timeout=EXEC_TIMEOUT_S, print_console=False)
    rocm_version = (_head_output(phdl, head_node, rocm_out) or '').strip() or None
    smi_out = phdl.exec('rocm-smi --showid 2>/dev/null', timeout=EXEC_TIMEOUT_S, print_console=False)
    # Anchor at line start like preflight_lib: incidental 'GPU[' substrings
    # elsewhere in the output must not inflate the count.
    gpu_count = len(re.findall(r'^GPU\[', _head_output(phdl, head_node, smi_out) or '', re.MULTILINE))
    return rocm_version, gpu_count or None


def _head_output(phdl, head_node, out):
    """Output string for *head_node*, or None if the node is unreachable.

    With stop_on_errors=False, Pssh stamps exception text plus an
    'ABORT: Host Unreachable Error' marker into the output dict for dead
    hosts (inform_unreachability) — truthy junk that must not land in
    baseline meta. Check both the pruned-host list and the marker.
    """
    if head_node in getattr(phdl, 'unreachable_hosts', ()):
        return None
    val = out.get(head_node) or ''
    if 'ABORT: Host Unreachable Error' in val:
        return None
    return val
