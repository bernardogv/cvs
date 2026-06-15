'''
Local, offline validation of cvs JSON input files against a command's declared
input contract (the ``input_files`` block from ``cvs describe``). Pure functions:
no SSH, no cluster. Catches a typo'd or malformed cluster/config file before a
long run, complementing preflight's cluster-side checks.
'''

import json
from pathlib import Path

SCHEMA_VERSION = 1


def validate_inputs(input_contracts, provided):
    '''Validate provided input files against their declared contracts.

    Args:
        input_contracts: list of dicts, each
            ``{"arg", "format", "required_keys", "optional_keys"}`` as emitted
            by ``cvs describe`` for a command.
        provided: mapping of contract ``arg`` -> file path (or ``None``/absent
            when the user did not supply that file).

    Returns:
        A validation-report dict
        ``{mode, schema_version, verdict, findings, warnings}``. Each finding is
        ``{file, arg, issue}`` (uniform keys, so ``validation_report`` can
        tabulate them). ``verdict`` is ``"pass"`` when there are no findings.
    '''
    findings = []
    warnings = []
    for contract in input_contracts:
        arg = contract['arg']
        path = provided.get(arg)
        if not path:
            warnings.append(f'{arg} not provided; skipping its checks')
            continue
        findings.extend(_validate_one(arg, path, contract.get('required_keys', [])))
    verdict = 'pass' if not findings else 'fail'
    return {
        'mode': 'validate',
        'schema_version': SCHEMA_VERSION,
        'verdict': verdict,
        'findings': findings,
        'warnings': warnings,
    }


def _validate_one(arg, path, required_keys):
    '''Findings for a single input file (empty list == valid).'''
    p = Path(path)
    if not p.exists():
        return [_finding(path, arg, 'file not found')]
    try:
        data = json.loads(p.read_text())
    except ValueError as exc:
        return [_finding(path, arg, f'invalid JSON: {exc}')]
    except OSError as exc:
        return [_finding(path, arg, f'cannot read file: {exc}')]
    if not isinstance(data, dict):
        return [_finding(path, arg, 'top-level JSON must be an object')]
    return [_finding(path, arg, f'missing required key "{key}"') for key in required_keys if key not in data]


def _finding(path, arg, issue):
    return {'file': str(path), 'arg': arg, 'issue': issue}
