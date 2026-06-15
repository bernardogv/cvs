import argparse
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from cvs.cli_plugins.run_json_plugin import RunJsonPlugin


JUNIT = '''<?xml version="1.0"?>
<testsuites><testsuite tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="m" name="ok" time="0.1"/>
  <testcase classname="m" name="bad" time="0.2"><failure message="boom">t</failure></testcase>
</testsuite></testsuites>'''

PASS_JUNIT = '''<?xml version="1.0"?>
<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">
  <testcase classname="m" name="ok" time="0.1"/>
</testsuite></testsuites>'''


class TestRunJsonPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = RunJsonPlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _run(self, argv, junit_text, pytest_rc=0, found='/x/test_agfhc.py'):
        args = self.parser.parse_args(argv)

        def fake_pytest_main(pytest_args, *a, **k):
            # Emulate pytest writing the junit file at the --junit-xml path.
            xml_path = next(x.split('=', 1)[1] for x in pytest_args if x.startswith('--junit-xml='))
            with open(xml_path, 'w') as fh:
                fh.write(junit_text)
            return pytest_rc

        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(self.plugin, '_find_test', return_value='cvs.tests.health.agfhc'),
            mock.patch.object(self.plugin, 'get_test_file', return_value=found),
            mock.patch('cvs.cli_plugins.run_json_plugin.pytest.main', side_effect=fake_pytest_main) as pmain,
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        return ctx.exception.code, out.getvalue(), err.getvalue(), pmain

    def test_failing_run_emits_json_and_exits_1(self):
        code, out, _, _ = self._run(
            ['run-json', 'agfhc', '--cluster_file', 'c.json', '--config_file', 'cfg.json'], JUNIT, pytest_rc=1
        )
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['mode'], 'run')
        self.assertEqual(report['summary']['failed'], 1)

    def test_passing_run_exits_0(self):
        code, out, _, _ = self._run(
            ['run-json', 'agfhc', '--cluster_file', 'c.json', '--config_file', 'cfg.json'], PASS_JUNIT, pytest_rc=0
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['verdict'], 'pass')

    def test_passes_cluster_and_config_and_junit_to_pytest(self):
        _, _, _, pmain = self._run(
            ['run-json', 'agfhc', '--cluster_file', 'c.json', '--config_file', 'cfg.json'], PASS_JUNIT
        )
        pytest_args = pmain.call_args[0][0]
        self.assertIn('--cluster_file=c.json', pytest_args)
        self.assertIn('--config_file=cfg.json', pytest_args)
        self.assertTrue(any(a.startswith('--junit-xml=') for a in pytest_args))

    def test_unknown_test_exits_2(self):
        args = self.parser.parse_args(['run-json', 'nope', '--cluster_file', 'c.json', '--config_file', 'cfg.json'])
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(self.plugin, '_find_test', return_value=None),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        self.assertEqual(ctx.exception.code, 2)

    def test_specific_functions_become_pytest_targets(self):
        _, _, _, pmain = self._run(
            ['run-json', 'agfhc', 'test_a', 'test_b', '--cluster_file', 'c.json', '--config_file', 'cfg.json'],
            PASS_JUNIT,
        )
        pytest_args = pmain.call_args[0][0]
        self.assertIn('/x/test_agfhc.py::test_a', pytest_args)
        self.assertIn('/x/test_agfhc.py::test_b', pytest_args)


if __name__ == '__main__':
    unittest.main()
