'''
Parse a pytest JUnit-XML file into the validation-report JSON contract so test
runs are machine-parseable (same shape as compare/preflight reports). JUnit XML
is pytest's stable built-in output, which keeps this decoupled from pytest
internals. Pure functions: feed XML text, get a report dict back.
'''

# Input is a temp file we generate ourselves from `pytest --junit-xml` (no
# untrusted/network data crosses this boundary), so XXE/entity-expansion is not
# a real vector. We still prefer defusedxml for defense-in-depth when it is
# installed, falling back to the stdlib parser without adding a dependency.
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

SCHEMA_VERSION = 1


def parse_junit_xml(xml_text):
    '''Convert JUnit-XML *xml_text* into a report dict.

    Returns ``{mode, schema_version, verdict, findings, tests, summary}``.
    ``findings`` lists failed/errored tests as ``{test, outcome, message}``
    (uniform keys for ``validation_report``); ``tests`` lists every case;
    ``summary`` counts ``total/passed/failed/errors/skipped``. ``verdict`` is
    ``"pass"`` only when there are no failures or errors.
    '''
    root = ET.fromstring(xml_text)
    tests = []
    findings = []
    counts = {'total': 0, 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    for case in root.iter('testcase'):
        name = _case_id(case)
        outcome, message = _classify(case)
        counts['total'] += 1
        counts[_count_key(outcome)] += 1
        tests.append({'test': name, 'outcome': outcome, 'time': case.get('time', '')})
        if outcome in ('failed', 'error'):
            findings.append({'test': name, 'outcome': outcome, 'message': message})
    verdict = 'pass' if not findings else 'fail'
    return {
        'mode': 'run',
        'schema_version': SCHEMA_VERSION,
        'verdict': verdict,
        'findings': findings,
        'tests': tests,
        'summary': counts,
    }


def _case_id(case):
    classname = case.get('classname', '')
    name = case.get('name', '')
    return f'{classname}::{name}' if classname else name


def _classify(case):
    '''(outcome, message) for a testcase element.'''
    failure = case.find('failure')
    if failure is not None:
        return 'failed', failure.get('message', '') or (failure.text or '').strip()
    error = case.find('error')
    if error is not None:
        return 'error', error.get('message', '') or (error.text or '').strip()
    if case.find('skipped') is not None:
        return 'skipped', ''
    return 'passed', ''


def _count_key(outcome):
    return {'passed': 'passed', 'failed': 'failed', 'error': 'errors', 'skipped': 'skipped'}[outcome]
