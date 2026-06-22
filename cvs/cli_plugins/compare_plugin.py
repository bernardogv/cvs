'''
cvs compare — peer / baseline / scaling comparison over aggregated rccl
result JSON files. Exit codes: 0 pass, 1 validation failure, 2 usage error.
'''

import sys
from pathlib import Path

import cvs.lib.compare_lib as compare_lib
import cvs.lib.validation_report as validation_report

from .base import SubcommandPlugin


def _add_common(parser):
    parser.add_argument('--format', choices=validation_report.FORMATS, default='table')
    parser.add_argument('--tolerance', type=float, default=None, help='deviation tolerance in percent')


class ComparePlugin(SubcommandPlugin):
    def get_name(self):
        return 'compare'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('compare', help='Compare rccl results: peers, baseline, or scaling')
        parser.set_defaults(_plugin=self)
        sub = parser.add_subparsers(dest='compare_mode', required=True)

        peers = sub.add_parser('peers', help='Each node vs fleet median (one file per node)')
        peers.add_argument('result_files', nargs='+', help='per-node aggregated result JSONs; node name = file stem')
        _add_common(peers)

        base = sub.add_parser('baseline', help='Current run vs a stored baseline')
        base.add_argument('result_file')
        base.add_argument('--against', required=True, help='baseline name')
        base.add_argument('--store', default=None, help='baseline store dir (default ~/.cvs/baselines)')
        _add_common(base)

        scaling = sub.add_parser('scaling', help='Curve shape across node counts')
        scaling.add_argument(
            'result_files', nargs='+', help='aggregated result JSONs from runs at different node counts'
        )
        _add_common(scaling)
        return parser

    def describe(self):
        return {
            'summary': 'Compare rccl results across peers, against a baseline, or along a scaling curve.',
            'read_only': True,
            'exit_codes': {'0': 'pass', '1': 'validation failure', '2': 'usage or tool error'},
            'examples': [
                'cvs compare peers node*.json --format json',
                'cvs compare baseline run.json --against gb200-2node --format json',
                'cvs compare scaling run_2n.json run_4n.json run_8n.json --format json',
            ],
        }

    def run(self, args):
        try:
            report = self._build_report(args)
        except (ValueError, FileNotFoundError, OSError) as exc:
            validation_report.emit_error(str(exc), args.format)
        print(validation_report.render(report, args.format))
        sys.exit(0 if report['verdict'] == 'pass' else 1)

    def _build_report(self, args):
        tol = {} if args.tolerance is None else {'tolerance_pct': args.tolerance}
        if args.compare_mode == 'peers':
            stems = [Path(f).stem for f in args.result_files]
            dupes = sorted({s for s in stems if stems.count(s) > 1})
            if dupes:
                raise ValueError(f'duplicate node names from file stems: {dupes}; rename files so each node is unique')
            node_results = {Path(f).stem: compare_lib.load_aggregated_results(f) for f in args.result_files}
            return compare_lib.compare_peers(node_results, **tol)
        if args.compare_mode == 'baseline':
            current = compare_lib.load_aggregated_results(args.result_file)
            baseline = compare_lib.load_baseline(args.against, store_dir=args.store)
            return compare_lib.compare_baseline(current, baseline, **tol)
        # scaling: node count comes from the rows' multinode metadata
        runs = []
        for f in args.result_files:
            rows = compare_lib.load_aggregated_rows(f)
            runs.append((_node_count_from_rows(f, rows), compare_lib._rows_to_map(rows)))
        return compare_lib.compare_scaling(runs, **tol)


def _node_count_from_rows(path, rows):
    """Read the 'nodes' field from the first row of an already-loaded result file."""
    if not rows or not rows[0].get('nodes'):
        raise ValueError(f'{path}: rows carry no "nodes" metadata; scaling mode needs multinode results')
    return int(rows[0]['nodes'])
