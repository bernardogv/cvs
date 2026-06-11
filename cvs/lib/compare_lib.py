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


# ---------------------------------------------------------------------------
# Task 4: baseline store + baseline comparison
# ---------------------------------------------------------------------------

DEFAULT_STORE_DIR = Path.home() / '.cvs' / 'baselines'


def make_baseline(results, meta=None):
    """Build a baseline dict from {key: busBw_mean} plus caller-supplied meta."""
    rows = [
        {'collective': k[0], 'size': k[1], 'dtype': k[2], 'in_place': k[3], 'bus_bw': v}
        for k, v in sorted(results.items())
    ]
    return {'schema_version': SCHEMA_VERSION, 'meta': dict(meta or {}), 'results': rows}


def baseline_results_map(baseline):
    """Inverse of make_baseline: baseline dict -> {key: busBw_mean}."""
    return {
        (r['collective'], int(r['size']), r['dtype'], int(r['in_place'])): float(r['bus_bw'])
        for r in baseline['results']
    }


def _baseline_path(name, store_dir=None):
    return Path(store_dir or DEFAULT_STORE_DIR) / f'{name}.json'


def save_baseline(baseline, name, store_dir=None):
    path = _baseline_path(name, store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2))
    return path


def load_baseline(name, store_dir=None):
    path = _baseline_path(name, store_dir)
    if not path.exists():
        raise FileNotFoundError(f'baseline "{name}" not found at {path}')
    return json.loads(path.read_text())


def list_baselines(store_dir=None):
    d = Path(store_dir or DEFAULT_STORE_DIR)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob('*.json'))


def delete_baseline(name, store_dir=None):
    _baseline_path(name, store_dir).unlink()


def compare_baseline(current, baseline, tolerance_pct=DEFAULT_TOLERANCE_PCT):
    """Compare {key: busBw_mean} against a stored baseline dict.

    Regressions beyond tolerance are findings (fail); improvements beyond
    tolerance are informational; keys present on only one side produce warnings.
    """
    base_map = baseline_results_map(baseline)
    findings, improvements, warnings = [], [], []
    common = sorted(set(current) & set(base_map))
    only_current = sorted(set(current) - set(base_map))
    only_base = sorted(set(base_map) - set(current))
    if only_current:
        warnings.append(f'not in baseline (skipped): {[_key_str(k) for k in only_current]}')
    if only_base:
        warnings.append(f'in baseline but not in this run: {[_key_str(k) for k in only_base]}')
    for key in common:
        ref = base_map[key]
        if ref <= 0:
            warnings.append(f'{_key_str(key)}: baseline value is 0; skipping')
            continue
        deviation_pct = (current[key] - ref) / ref * 100.0
        name, size, dtype, in_place = key
        entry = {
            'collective': name,
            'size': size,
            'dtype': dtype,
            'in_place': in_place,
            'bus_bw': current[key],
            'baseline_bus_bw': ref,
            'deviation_pct': round(deviation_pct, 2),
        }
        if deviation_pct < -tolerance_pct:
            findings.append(entry)
        elif deviation_pct > tolerance_pct:
            improvements.append(entry)
    return _report('baseline', findings, warnings, tolerance_pct,
                   baseline_name=baseline.get('meta', {}).get('name', ''),
                   improvements=improvements, points_compared=len(common))


# ---------------------------------------------------------------------------
# Task 5: scaling-curve comparison
# ---------------------------------------------------------------------------

# Collectives whose busBw is expected to stay roughly flat as node count grows
# on a healthy fabric. Conservative starter set; tune against real data.
SCALING_FLAT_COLLECTIVES = {'AllReduce', 'AllGather', 'ReduceScatter', 'Broadcast'}
DEFAULT_SCALING_TOLERANCE_PCT = 15.0


def compare_scaling(runs, tolerance_pct=DEFAULT_SCALING_TOLERANCE_PCT):
    """Validate curve shape across node counts.

    runs: list of (node_count, {key: busBw_mean}). The smallest node count is
    the reference; larger runs whose busBw sags more than tolerance below the
    reference (for flat-expectation collectives) are findings.
    """
    if len(runs) < 2:
        raise ValueError('compare_scaling needs at least two runs at different node counts')
    runs = sorted(runs, key=lambda r: r[0])
    ref_n, ref_map = runs[0]
    findings, warnings = [], []
    points = 0
    for node_count, res in runs[1:]:
        for key in sorted(res):
            name, size, dtype, in_place = key
            if name not in SCALING_FLAT_COLLECTIVES:
                continue
            if key not in ref_map:
                warnings.append(f'{_key_str(key)}: missing in {ref_n}-node reference run')
                continue
            ref = ref_map[key]
            if ref <= 0:
                warnings.append(f'{_key_str(key)}: reference value is 0; skipping')
                continue
            points += 1
            deviation_pct = (res[key] - ref) / ref * 100.0
            if deviation_pct < -tolerance_pct:
                findings.append({
                    'collective': name,
                    'size': size,
                    'dtype': dtype,
                    'in_place': in_place,
                    'node_count': node_count,
                    'bus_bw': res[key],
                    'reference_node_count': ref_n,
                    'reference_bus_bw': ref,
                    'deviation_pct': round(deviation_pct, 2),
                })
    return _report('scaling', findings, warnings, tolerance_pct,
                   node_counts=[n for n, _ in runs], points_compared=points)
