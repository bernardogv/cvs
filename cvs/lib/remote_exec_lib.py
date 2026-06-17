'''
Turn Pssh.exec's merged per-host text into the machine-readable validation-report
contract: per-node reachability, exit code, and clean output. Real per-node exit
codes are recovered by appending an exit-code sentinel to the command (Pssh.exec
exposes no exit status), so this needs no change to core parallel-ssh. Pure
functions: feed the raw {host: output} dict, get a report dict back.
'''

import re

SCHEMA_VERSION = 1
EXIT_SENTINEL = '__CVS_EXIT__'
_UNREACHABLE_MARKER = 'ABORT: Host Unreachable Error'
_RE_EXIT = re.compile(r'__CVS_EXIT__(\d+)__')


def wrap_command(cmd):
    '''Append an exit-code marker so the per-host rc survives in merged output.'''
    return f'{cmd}; printf "\\n{EXIT_SENTINEL}%s__\\n" "$?"'


def build_exec_report(cmd, raw_output, unreachable_hosts):
    '''Build the exec report from Pssh.exec output.

    Args:
        cmd: the original (unwrapped) command the user asked to run.
        raw_output: ``{host: combined_output_str}`` from ``Pssh.exec``.
        unreachable_hosts: ``Pssh.unreachable_hosts`` after the exec.

    Returns ``{mode, schema_version, command, verdict, nodes, findings, warnings}``.
    ``nodes`` has every host with ``{node, reachable, exit_code, output}``;
    ``findings`` lists problems as ``{node, issue}`` (uniform keys). ``verdict``
    is ``"pass"`` only when every node is reachable and exited 0.
    '''
    unreachable = set(unreachable_hosts or [])
    nodes = []
    findings = []
    for host, out in raw_output.items():
        out = out or ''
        if host in unreachable or _UNREACHABLE_MARKER in out:
            nodes.append({'node': host, 'reachable': False, 'exit_code': None, 'output': out.strip()})
            findings.append({'node': host, 'issue': 'unreachable'})
            continue
        exit_code, clean = _extract_exit(out)
        nodes.append({'node': host, 'reachable': True, 'exit_code': exit_code, 'output': clean})
        if exit_code is None:
            findings.append({'node': host, 'issue': 'no exit code captured'})
        elif exit_code != 0:
            findings.append({'node': host, 'issue': f'exit code {exit_code}'})
    nodes.sort(key=lambda n: n['node'])
    findings.sort(key=lambda f: f['node'])
    return {
        'mode': 'exec',
        'schema_version': SCHEMA_VERSION,
        'command': cmd,
        'verdict': 'pass' if not findings else 'fail',
        'nodes': nodes,
        'findings': findings,
        'warnings': [],
    }


def build_dry_run_report(cmd, nodes):
    '''Preview report: what exec-json WOULD run, without touching any node.

    Same ``mode='exec'`` shape (so it renders identically), with ``dry_run`` set
    and each target node listed as a ``would-run`` finding. Verdict is always
    ``pass`` (a preview never fails / always exits 0).
    '''
    return {
        'mode': 'exec',
        'schema_version': SCHEMA_VERSION,
        'verdict': 'pass',
        'dry_run': True,
        'command': cmd,
        'nodes': [{'node': n, 'reachable': None, 'exit_code': None, 'output': ''} for n in nodes],
        'findings': [{'node': n, 'action': 'would-run'} for n in nodes],
        'warnings': [f'dry-run: would run {cmd!r} on {len(nodes)} node(s); nothing was executed'],
    }


def _extract_exit(out):
    '''(exit_code, output-with-sentinels-removed); exit_code is None if absent.'''
    matches = list(_RE_EXIT.finditer(out))
    if not matches:
        return None, out.strip()
    code = int(matches[-1].group(1))
    return code, _RE_EXIT.sub('', out).strip()
