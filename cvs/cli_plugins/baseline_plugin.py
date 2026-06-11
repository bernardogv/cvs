'''
cvs baseline — capture/list/show/delete stored known-good result fingerprints.
Exit codes: 0 ok, 2 usage/tool error.
'''

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cvs.lib.compare_lib as compare_lib

from .base import SubcommandPlugin


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
            results = compare_lib.load_aggregated_results(args.result_file)
            rows = json.loads(Path(args.result_file).read_text())
            meta = {
                'name': name,
                'captured': datetime.now(timezone.utc).isoformat(),
                'node_count': rows[0].get('nodes') if rows else None,
                'source_result_file': str(args.result_file),
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
