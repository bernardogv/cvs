'''
No-SSH end-to-end smoke for `cvs run-json`: drives the REAL pipeline
(_run_and_parse -> real pytest -> JUnit-XML -> parse -> JSON contract) against a
throwaway pytest suite with no cluster/SSH. Run in a subprocess so the inner
pytest is not nested inside this outer pytest run. Proves the contract end to end
and that selecting one parametrized case runs exactly that case.
'''

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Minimal conftest so the dummy suite accepts the cluster/config options that
# run-json always forwards (mirrors what the real cvs conftest provides).
DUMMY_CONFTEST = textwrap.dedent('''
    def pytest_addoption(parser):
        parser.addoption("--cluster_file", action="store")
        parser.addoption("--config_file", action="store")
''')

# A parametrized passing test (two cases) + one guaranteed failure, so the report
# exercises pass/fail counts, findings, and per-case selection. No SSH, no GPUs.
DUMMY_TEST = textwrap.dedent('''
    import pytest

    @pytest.mark.parametrize("collective", ["all_reduce", "all_gather"])
    def test_collective(collective):
        assert collective in ("all_reduce", "all_gather")

    def test_always_fails():
        assert False, "boom"
''')

# Runs in the subprocess: call the real run-json internals, print the report.
DRIVER = textwrap.dedent('''
    import json, sys
    from cvs.cli_plugins.run_json_plugin import RunJsonPlugin
    test_file, *funcs = sys.argv[1:]
    report = RunJsonPlugin()._run_and_parse(test_file, funcs, "c.json", "cfg.json")
    print("REPORT_JSON:" + json.dumps(report))
''')


class TestRunJsonSmokeNoSSH(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / 'conftest.py').write_text(DUMMY_CONFTEST)
        self.test_file = d / 'test_dummy.py'
        self.test_file.write_text(DUMMY_TEST)

    def _drive(self, *funcs):
        proc = subprocess.run(
            [sys.executable, '-c', DRIVER, str(self.test_file), *funcs],
            capture_output=True,
            text=True,
            timeout=120,
        )
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith('REPORT_JSON:')]
        self.assertTrue(lines, f'no report emitted.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}')
        return json.loads(lines[0][len('REPORT_JSON:') :])

    def test_full_run_emits_contract(self):
        report = self._drive()
        self.assertEqual(report['mode'], 'run')
        self.assertEqual(report['schema_version'], 1)
        # two parametrized cases pass, one test fails -> overall fail
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['summary']['passed'], 2)
        self.assertEqual(report['summary']['failed'], 1)
        self.assertTrue(any('test_always_fails' in f['test'] for f in report['findings']))

    def test_selecting_one_parametrized_case_runs_only_that(self):
        report = self._drive('test_collective[all_reduce]')
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['summary']['total'], 1)
        self.assertEqual(len(report['tests']), 1)
        self.assertEqual(report['tests'][0]['outcome'], 'passed')
        self.assertIn('all_reduce', report['tests'][0]['test'])


if __name__ == '__main__':
    unittest.main()
