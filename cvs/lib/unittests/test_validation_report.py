import contextlib
import csv
import io
import json
import unittest

import cvs.lib.compare_lib as compare_lib
import cvs.lib.validation_report as validation_report
from cvs.lib.unittests.fixtures.gen_rccl_fixtures import make_rows


def _fail_report():
    fleet = {f'node{i}': compare_lib._rows_to_map(make_rows()) for i in range(1, 4)}
    fleet['node3'] = compare_lib._rows_to_map(make_rows(scale=0.85))
    return compare_lib.compare_peers(fleet)


class TestRender(unittest.TestCase):
    def test_json_roundtrips(self):
        report = _fail_report()
        out = validation_report.render(report, 'json')
        self.assertEqual(json.loads(out), report)

    def test_table_contains_verdict_and_findings(self):
        out = validation_report.render(_fail_report(), 'table')
        self.assertIn('FAIL', out)
        self.assertIn('node3', out)
        self.assertIn('AllReduce', out)

    def test_csv_has_header_and_rows(self):
        report = _fail_report()
        rows = list(csv.DictReader(io.StringIO(validation_report.render(report, 'csv'))))
        self.assertEqual(len(rows), len(report['findings']))
        self.assertIn('deviation_pct', rows[0])

    def test_csv_empty_findings_returns_empty_string(self):
        fleet = {f'node{i}': compare_lib._rows_to_map(make_rows()) for i in range(1, 4)}
        report = compare_lib.compare_peers(fleet)
        out = validation_report.render(report, 'csv')
        self.assertEqual(out.strip(), '')

    def test_table_improvements_render_as_key_value_pairs(self):
        baseline = compare_lib.make_baseline(compare_lib._rows_to_map(make_rows()))
        report = compare_lib.compare_baseline(compare_lib._rows_to_map(make_rows(scale=1.2)), baseline)
        self.assertTrue(report['improvements'])
        out = validation_report.render(report, 'table')
        self.assertIn('improvement: collective=', out)

    def test_table_preflight_report_omits_absent_fields(self):
        report = {
            'schema_version': 1,
            'mode': 'preflight',
            'verdict': 'pass',
            'findings': [],
            'warnings': [],
            'checks': [],
            'nodes': 2,
        }
        out = validation_report.render(report, 'table')
        self.assertIn('PASS', out)
        self.assertNotIn('None%', out)
        self.assertNotIn('points_compared', out)

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            validation_report.render(_fail_report(), 'yaml')


class TestEmitError(unittest.TestCase):
    def _emit(self, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                validation_report.emit_error(**kw)
        return ctx.exception.code, out.getvalue(), err.getvalue()

    def test_json_error_is_structured_on_stdout(self):
        code, out, err = self._emit(message="unknown test 'foo'", fmt='json', hint='run cvs list')
        self.assertEqual(code, 2)
        self.assertEqual(err, '')  # nothing to scrape on stderr
        report = json.loads(out)
        self.assertEqual(report['verdict'], 'error')
        self.assertEqual(report['mode'], 'error')
        self.assertEqual(report['error'], {'message': "unknown test 'foo'", 'hint': 'run cvs list'})

    def test_human_format_goes_to_stderr(self):
        code, out, err = self._emit(message='bad', fmt='table', hint='try again')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('error: bad', err)
        self.assertIn('hint: try again', err)

    def test_custom_exit_code(self):
        code, _, _ = self._emit(message='x', fmt='json', exit_code=1)
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
