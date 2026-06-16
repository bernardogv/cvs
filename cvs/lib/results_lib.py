'''
Render a single rccl run's aggregated results as a clean summary: bus bandwidth
per collective x message size, optionally against the config's expected
thresholds with a pass/fail verdict. Pure functions producing a
validation-report dict (so validation_report renders it as table/csv/json).
Complements `compare` (peer/baseline/scaling) by summarizing one run.
'''

SCHEMA_VERSION = 1


def thresholds_from_config(config):
    '''Extract ``{collective: {size_str: threshold}}`` from a parsed config dict.

    Reads ``rccl.results.<collective>.bus_bw.<size_bytes>``; returns ``{}`` when
    no thresholds are present.
    '''
    results = config.get('rccl', {}).get('results', {})
    out = {}
    for collective, body in results.items():
        bus_bw = (body or {}).get('bus_bw', {})
        out[collective] = {str(size): val for size, val in bus_bw.items()}
    return out


def build_results_report(rows, expected=None):
    '''Summarize aggregated-result *rows* into a validation-report dict.

    Args:
        rows: aggregated-result dicts (``compare_lib.load_aggregated_rows``
            output): each has ``name``, ``size``, ``busBw_mean``, optional
            ``busBw_std`` and ``nodes``.
        expected: optional ``{collective: {size_str: threshold}}`` (see
            ``thresholds_from_config``). When given, each row is graded
            PASS/FAIL against its threshold and the verdict fails if any row is
            below. When absent, numbers are shown informationally (verdict pass).

    Returns ``{mode, schema_version, verdict, nodes?, findings, warnings}``;
    each finding is ``{collective, size, busBw_GB_s, expected, status}``.
    '''
    have_expected = bool(expected)
    findings = []
    nodes = None
    any_fail = False
    for row in sorted(rows, key=lambda r: (r['name'], int(r['size']))):
        collective = row['name']
        size = int(row['size'])
        mean = float(row['busBw_mean'])
        std = row.get('busBw_std')
        nodes = nodes or row.get('nodes')

        bus_bw = f'{mean:.1f}' + (f' ±{float(std):.1f}' if std is not None else '')
        threshold = expected.get(collective, {}).get(str(size)) if have_expected else None
        if threshold is not None:
            status = 'PASS' if mean >= float(threshold) else 'FAIL'
            any_fail = any_fail or status == 'FAIL'
            expected_str = f'{float(threshold):.2f}'
        else:
            status = '-'
            expected_str = '-'
        findings.append(
            {
                'collective': collective,
                'size': _human_size(size),
                'busBw_GB_s': bus_bw,
                'expected': expected_str,
                'status': status,
            }
        )

    report = {
        'mode': 'results',
        'schema_version': SCHEMA_VERSION,
        'verdict': 'fail' if any_fail else 'pass',
        'findings': findings,
        'warnings': [],
    }
    if nodes:
        report['nodes'] = nodes
    if not have_expected:
        report['warnings'].append('no --config given; showing measured numbers only (no pass/fail)')
    return report


def _human_size(num_bytes):
    '''Bytes -> a compact binary size like "8 GiB" / "1.5 MiB".'''
    size = float(num_bytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or unit == 'TiB':
            if unit == 'B':
                return f'{int(size)} {unit}'
            return f'{size:.0f} {unit}' if size == int(size) else f'{size:.1f} {unit}'
        size /= 1024
