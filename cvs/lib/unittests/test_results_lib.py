import unittest

import cvs.lib.results_lib as results_lib


def _row(name, size, mean, std=None, nodes=2):
    r = {'name': name, 'size': size, 'type': 'float', 'inPlace': 1, 'busBw_mean': mean}
    if std is not None:
        r['busBw_std'] = std
    if nodes is not None:
        r['nodes'] = nodes
    return r


ROWS = [
    _row('all_reduce_perf', 17179869184, 351.0, std=0.8),
    _row('all_reduce_perf', 8589934592, 358.2, std=1.1),
    _row('alltoall_perf', 8589934592, 46.1, std=0.3),
]

# {collective: {size_str: threshold}}
EXPECTED = {
    'all_reduce_perf': {'8589934592': '330.00', '17179869184': '350.00'},
    'alltoall_perf': {'8589934592': '45.00'},
}


class TestThresholdsFromConfig(unittest.TestCase):
    def test_extracts_collective_size_thresholds(self):
        config = {'rccl': {'results': {'all_reduce_perf': {'bus_bw': {'8589934592': '330.00'}}}}}
        out = results_lib.thresholds_from_config(config)
        self.assertEqual(out['all_reduce_perf']['8589934592'], '330.00')

    def test_missing_results_returns_empty(self):
        self.assertEqual(results_lib.thresholds_from_config({'rccl': {}}), {})


class TestBuildResultsReport(unittest.TestCase):
    def test_no_expected_shows_numbers_and_passes(self):
        report = results_lib.build_results_report(ROWS, expected=None)
        self.assertEqual(report['mode'], 'results')
        self.assertEqual(report['verdict'], 'pass')  # informational
        self.assertEqual(report['nodes'], 2)
        self.assertEqual(len(report['findings']), 3)
        self.assertTrue(all(f['status'] == '-' for f in report['findings']))
        self.assertTrue(any('no --config' in w for w in report['warnings']))

    def test_rows_sorted_by_collective_then_size(self):
        report = results_lib.build_results_report(ROWS, expected=None)
        order = [(f['collective'], f['size']) for f in report['findings']]
        self.assertEqual(
            order,
            [('all_reduce_perf', '8 GiB'), ('all_reduce_perf', '16 GiB'), ('alltoall_perf', '8 GiB')],
        )

    def test_busbw_formats_mean_and_std(self):
        report = results_lib.build_results_report(ROWS, expected=None)
        first = report['findings'][0]
        self.assertEqual(first['busBw_GB_s'], '358.2 ±1.1')

    def test_all_above_expected_passes(self):
        report = results_lib.build_results_report(ROWS, expected=EXPECTED)
        self.assertEqual(report['verdict'], 'pass')
        self.assertTrue(all(f['status'] == 'PASS' for f in report['findings']))
        ar8 = next(f for f in report['findings'] if f['collective'] == 'all_reduce_perf' and f['size'] == '8 GiB')
        self.assertEqual(ar8['expected'], '330.00')

    def test_below_expected_fails_that_row(self):
        rows = [_row('all_reduce_perf', 8589934592, 300.0)]  # below 330 threshold
        report = results_lib.build_results_report(rows, expected=EXPECTED)
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['findings'][0]['status'], 'FAIL')

    def test_uniform_finding_keys(self):
        report = results_lib.build_results_report(ROWS, expected=EXPECTED)
        keys = {k for f in report['findings'] for k in f}
        self.assertEqual(keys, {'collective', 'size', 'busBw_GB_s', 'expected', 'status'})


if __name__ == '__main__':
    unittest.main()
