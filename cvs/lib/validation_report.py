'''
Render compare_lib / preflight_lib report dicts as table, csv, or json.
json output is the machine contract; table is for humans; csv is findings-only.
'''
import csv
import io
import json

FORMATS = ('table', 'csv', 'json')


def render(report, fmt):
    """Render *report* in *fmt*; returns a string. Raises ValueError for unknown formats."""
    if fmt == 'json':
        return json.dumps(report, indent=2)
    if fmt == 'csv':
        return _render_csv(report)
    if fmt == 'table':
        return _render_table(report)
    raise ValueError(f'unknown format {fmt!r}; expected one of {FORMATS}')


def _render_csv(report):
    findings = report.get('findings', [])
    if not findings:
        return ''
    buf = io.StringIO()
    # All findings within one report share the same key set (true for all
    # compare modes and planned preflight findings), so findings[0] is a
    # safe source of column names.
    writer = csv.DictWriter(buf, fieldnames=list(findings[0].keys()))
    writer.writeheader()
    writer.writerows(findings)
    return buf.getvalue()


def _render_table(report):
    lines = []
    verdict = report.get('verdict', 'unknown').upper()
    lines.append(f"[{verdict}] mode={report.get('mode')} "
                 f"tolerance={report.get('tolerance_pct')}% "
                 f"points_compared={report.get('points_compared', 'n/a')}")
    findings = report.get('findings', [])
    if findings:
        cols = list(findings[0].keys())
        widths = {c: max(len(c), max(len(str(f[c])) for f in findings)) for c in cols}
        lines.append('  ' + '  '.join(c.ljust(widths[c]) for c in cols))
        for f in findings:
            lines.append('  ' + '  '.join(str(f[c]).ljust(widths[c]) for c in cols))
    else:
        lines.append('  no findings')
    for imp in report.get('improvements', []):
        lines.append('  improvement: ' + '  '.join(f'{k}={v}' for k, v in imp.items()))
    for w in report.get('warnings', []):
        lines.append(f'  warning: {w}')
    return '\n'.join(lines)
