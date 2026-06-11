'''
Pure-function comparison engine for cluster validation.

Inputs are JSON files containing a list of RcclTestsAggregated dicts
(cvs/schema/rccl.py) as written by cvs.lib.rccl_lib. No SSH, no cluster.

Report dicts returned by compare_* functions are a STABLE CONTRACT
(schema_version 1) consumed by the cluster-validation MCP layer
(~/Projects/amd/cluster-validation-plugin). Changing shapes requires a
schema_version bump and a contract-test update there.
'''
import json
import statistics
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_TOLERANCE_PCT = 5.0
_MIN_NODES_FOR_MEDIAN = 3

# A result key: (collective, size_bytes, dtype, in_place)


def _key_str(key):
    name, size, dtype, in_place = key
    return f'{name}/{size}/{dtype}/inPlace={in_place}'


def load_aggregated_results(path):
    """Load an aggregated rccl result JSON file into {key: busBw_mean}."""
    path = Path(path)
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f'{path}: expected a JSON list of aggregated results')
    out = {}
    for row in data:
        try:
            key = (row['name'], int(row['size']), row['type'], int(row['inPlace']))
            out[key] = float(row['busBw_mean'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f'{path}: invalid aggregated-result row {row!r}: {exc}'
            ) from exc
    return out


def _rows_to_map(rows):
    """Convert a list of aggregated-result dicts to {key: busBw_mean}."""
    return {
        (r['name'], int(r['size']), r['type'], int(r['inPlace'])): float(r['busBw_mean'])
        for r in rows
    }


def _report(mode, findings, warnings, tolerance_pct, **extra):
    return {
        **extra,
        'schema_version': SCHEMA_VERSION,
        'mode': mode,
        'tolerance_pct': tolerance_pct,
        'verdict': 'fail' if findings else 'pass',
        'findings': findings,
        'warnings': warnings,
    }


def compare_peers(node_results, tolerance_pct=DEFAULT_TOLERANCE_PCT):
    """Flag nodes whose busBw sits more than tolerance below the fleet median.

    node_results: {node_name: {key: busBw_mean}} — one entry per node from a
    parallel single-node run.
    """
    findings, warnings = [], []
    points = 0
    all_keys = set()
    for res in node_results.values():
        all_keys.update(res)
    for key in sorted(all_keys):
        values = {n: r[key] for n, r in node_results.items() if key in r}
        missing = sorted(set(node_results) - set(values))
        if missing:
            warnings.append(f'{_key_str(key)}: missing on nodes {missing}')
        if len(values) < _MIN_NODES_FOR_MEDIAN:
            warnings.append(
                f'{_key_str(key)}: only {len(values)} node(s) have data; '
                f'skipping (need >= {_MIN_NODES_FOR_MEDIAN} for a meaningful median)'
            )
            continue
        median = statistics.median(values.values())
        if median <= 0:
            warnings.append(f'{_key_str(key)}: fleet median is 0; skipping')
            continue
        points += len(values)
        for node, bus_bw in sorted(values.items()):
            deviation_pct = (bus_bw - median) / median * 100.0
            if deviation_pct < -tolerance_pct:
                name, size, dtype, in_place = key
                findings.append({
                    'node': node,
                    'collective': name,
                    'size': size,
                    'dtype': dtype,
                    'in_place': in_place,
                    'bus_bw': bus_bw,
                    'fleet_median': median,
                    'deviation_pct': round(deviation_pct, 2),
                })
    return _report('peers', findings, warnings, tolerance_pct,
                   nodes=len(node_results), points_compared=points)
