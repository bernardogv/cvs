'''
Render compare_lib / preflight_lib report dicts as table, csv, or json.
json output is the machine contract; table is for humans; csv is findings-only.
'''

import csv
import io
import json
import sys

FORMATS = ('table', 'csv', 'json')


def emit_error(message, fmt='json', hint=None, exit_code=2):
    '''Emit a usage/tool error on the SAME contract, then exit.

    With ``fmt='json'`` an agent never has to parse a string — even on failure:
    a structured ``{verdict:"error", error:{message,hint}}`` goes to stdout (the
    one stream it already reads). For human formats the text goes to stderr.
    Always calls ``sys.exit(exit_code)`` (default 2 = usage/tool error).
    '''
    if fmt == 'json':
        report = {
            'mode': 'error',
            'schema_version': 1,
            'verdict': 'error',
            'error': {'message': message, 'hint': hint},
        }
        print(json.dumps(report, indent=2))
    else:
        print(f'error: {message}', file=sys.stderr)
        if hint:
            print(f'hint: {hint}', file=sys.stderr)
    sys.exit(exit_code)


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
    header = [f"[{verdict}]", f"mode={report.get('mode')}"]
    # Preflight reports carry neither field; omit rather than render 'None%'.
    if report.get('tolerance_pct') is not None:
        header.append(f"tolerance={report['tolerance_pct']}%")
    if 'points_compared' in report:
        header.append(f"points_compared={report['points_compared']}")
    lines.append(' '.join(header))
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
