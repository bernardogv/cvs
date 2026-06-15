import unittest

import cvs.lib.junit_report_lib as jr


PASS_XML = '''<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2" failures="0" errors="0" skipped="0">
  <testcase classname="cvs.tests.health.agfhc" name="test_a" time="1.5"/>
  <testcase classname="cvs.tests.health.agfhc" name="test_b" time="0.5"/>
</testsuite></testsuites>'''

MIXED_XML = '''<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
  <testcase classname="m" name="ok" time="0.1"/>
  <testcase classname="m" name="bad" time="0.2"><failure message="assert 1 == 2">trace</failure></testcase>
  <testcase classname="m" name="broke" time="0.0"><error message="ssh down">trace</error></testcase>
  <testcase classname="m" name="skip" time="0.0"><skipped message="no gpu"/></testcase>
</testsuite></testsuites>'''


class TestParseJunit(unittest.TestCase):
    def test_all_pass(self):
        report = jr.parse_junit_xml(PASS_XML)
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['mode'], 'run')
        self.assertEqual(report['schema_version'], jr.SCHEMA_VERSION)
        self.assertEqual(report['summary']['passed'], 2)
        self.assertEqual(report['findings'], [])
        self.assertEqual(len(report['tests']), 2)

    def test_failures_and_errors_make_findings(self):
        report = jr.parse_junit_xml(MIXED_XML)
        self.assertEqual(report['verdict'], 'fail')
        outcomes = {f['test']: f['outcome'] for f in report['findings']}
        self.assertEqual(outcomes['m::bad'], 'failed')
        self.assertEqual(outcomes['m::broke'], 'error')
        # skipped is not a finding (not a failure), but is counted.
        self.assertNotIn('m::skip', outcomes)
        self.assertEqual(report['summary'], {'total': 4, 'passed': 1, 'failed': 1, 'errors': 1, 'skipped': 1})
        # findings carry the message for an agent to read.
        bad = next(f for f in report['findings'] if f['test'] == 'm::bad')
        self.assertIn('assert', bad['message'])

    def test_findings_have_uniform_keys(self):
        report = jr.parse_junit_xml(MIXED_XML)
        self.assertEqual({k for f in report['findings'] for k in f}, {'test', 'outcome', 'message'})

    def test_empty_suite_passes(self):
        report = jr.parse_junit_xml('<testsuites></testsuites>')
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['summary']['total'], 0)


if __name__ == '__main__':
    unittest.main()
