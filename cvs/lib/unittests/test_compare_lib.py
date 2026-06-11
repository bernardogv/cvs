import json
import tempfile
import unittest
from pathlib import Path

import cvs.lib.compare_lib as compare_lib
from cvs.lib.unittests.fixtures.gen_rccl_fixtures import make_rows


def write_results(tmpdir, name, rows):
    p = Path(tmpdir) / f'{name}.json'
    p.write_text(json.dumps(rows))
    return p


class TestLoadAggregatedResults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_loads_keys_and_bus_bw(self):
        p = write_results(self.tmp.name, 'node1', make_rows())
        res = compare_lib.load_aggregated_results(p)
        self.assertEqual(res[('AllReduce', 8589934592, 'float', 0)], 330.0)
        self.assertEqual(len(res), 6)

    def test_rejects_non_list(self):
        p = Path(self.tmp.name) / 'bad.json'
        p.write_text('{"name": "AllReduce"}')
        with self.assertRaises(ValueError):
            compare_lib.load_aggregated_results(p)

    def test_rejects_row_missing_fields(self):
        p = write_results(self.tmp.name, 'bad', [{'name': 'AllReduce', 'size': 1}])
        with self.assertRaises(ValueError):
            compare_lib.load_aggregated_results(p)


class TestComparePeers(unittest.TestCase):
    def _fleet(self, n=4):
        return {f'node{i}': compare_lib._rows_to_map(make_rows()) for i in range(1, n + 1)}

    def test_healthy_fleet_passes(self):
        report = compare_lib.compare_peers(self._fleet())
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['mode'], 'peers')
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['nodes'], 4)

    def test_slow_node_flagged(self):
        fleet = self._fleet()
        fleet['node3'] = compare_lib._rows_to_map(make_rows(scale=0.9))  # 10% slow
        report = compare_lib.compare_peers(fleet, tolerance_pct=5.0)
        self.assertEqual(report['verdict'], 'fail')
        flagged_nodes = {f['node'] for f in report['findings']}
        self.assertEqual(flagged_nodes, {'node3'})
        f = report['findings'][0]
        self.assertLess(f['deviation_pct'], -5.0)
        self.assertIn('collective', f)
        self.assertIn('fleet_median', f)

    def test_slow_node_within_tolerance_passes(self):
        fleet = self._fleet()
        fleet['node3'] = compare_lib._rows_to_map(make_rows(scale=0.97))  # 3% slow
        report = compare_lib.compare_peers(fleet, tolerance_pct=5.0)
        self.assertEqual(report['verdict'], 'pass')

    def test_missing_key_warns(self):
        fleet = self._fleet()
        del fleet['node2'][('AllReduce', 1048576, 'float', 0)]
        report = compare_lib.compare_peers(fleet)
        self.assertTrue(any('node2' in w for w in report['warnings']))

    def test_report_contract_shape(self):
        fleet = self._fleet()
        fleet['node3'] = compare_lib._rows_to_map(make_rows(scale=0.9))  # 10% slow
        report = compare_lib.compare_peers(fleet)
        self.assertEqual(
            set(report),
            {'schema_version', 'mode', 'tolerance_pct', 'verdict', 'findings', 'warnings', 'nodes', 'points_compared'},
        )
        self.assertTrue(report['findings'])
        for finding in report['findings']:
            self.assertEqual(
                set(finding),
                {'node', 'collective', 'size', 'dtype', 'in_place', 'bus_bw', 'fleet_median', 'deviation_pct'},
            )

    def test_fewer_than_three_nodes_skips_with_warning(self):
        report = compare_lib.compare_peers(self._fleet(n=2))
        self.assertEqual(report['verdict'], 'pass')
        self.assertTrue(any('need >= 3' in w for w in report['warnings']))


class TestBaseline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name)

    def test_save_and_load_roundtrip(self):
        results = compare_lib._rows_to_map(make_rows())
        baseline = compare_lib.make_baseline(results, meta={'name': 'test-2n', 'node_count': 2})
        path = compare_lib.save_baseline(baseline, 'test-2n', store_dir=self.store)
        self.assertTrue(path.exists())
        loaded = compare_lib.load_baseline('test-2n', store_dir=self.store)
        self.assertEqual(loaded['meta']['name'], 'test-2n')
        self.assertEqual(compare_lib.baseline_results_map(loaded), results)

    def test_list_baselines(self):
        b = compare_lib.make_baseline(compare_lib._rows_to_map(make_rows()), meta={'name': 'a'})
        compare_lib.save_baseline(b, 'a', store_dir=self.store)
        compare_lib.save_baseline(b, 'b', store_dir=self.store)
        self.assertEqual(compare_lib.list_baselines(store_dir=self.store), ['a', 'b'])

    def test_load_missing_baseline_raises(self):
        with self.assertRaises(FileNotFoundError):
            compare_lib.load_baseline('nope', store_dir=self.store)

    def test_name_escaping_store_dir_raises(self):
        b = compare_lib.make_baseline(compare_lib._rows_to_map(make_rows()), meta={'name': 'evil'})
        with self.assertRaises(ValueError):
            compare_lib.save_baseline(b, '../evil', store_dir=self.store)

    def test_delete_baseline(self):
        b = compare_lib.make_baseline(compare_lib._rows_to_map(make_rows()), meta={'name': 'a'})
        compare_lib.save_baseline(b, 'a', store_dir=self.store)
        compare_lib.delete_baseline('a', store_dir=self.store)
        self.assertEqual(compare_lib.list_baselines(store_dir=self.store), [])

    def test_delete_missing_baseline_raises(self):
        with self.assertRaises(FileNotFoundError):
            compare_lib.delete_baseline('nope', store_dir=self.store)


class TestCompareBaseline(unittest.TestCase):
    def _baseline(self):
        return compare_lib.make_baseline(compare_lib._rows_to_map(make_rows()), meta={'name': 'good'})

    def test_identical_run_passes(self):
        current = compare_lib._rows_to_map(make_rows())
        report = compare_lib.compare_baseline(current, self._baseline())
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['findings'], [])

    def test_regression_flagged(self):
        current = compare_lib._rows_to_map(make_rows(scale=0.88))  # 12% down
        report = compare_lib.compare_baseline(current, self._baseline(), tolerance_pct=5.0)
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(len(report['findings']), 6)
        f = report['findings'][0]
        self.assertIn('baseline_bus_bw', f)
        self.assertLess(f['deviation_pct'], -5.0)

    def test_improvement_reported_not_failed(self):
        current = compare_lib._rows_to_map(make_rows(scale=1.2))
        report = compare_lib.compare_baseline(current, self._baseline(), tolerance_pct=5.0)
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(len(report['improvements']), 6)

    def test_non_overlapping_keys_warn(self):
        current = compare_lib._rows_to_map(make_rows(dtype='bfloat16'))
        report = compare_lib.compare_baseline(current, self._baseline())
        self.assertEqual(report['verdict'], 'pass')  # nothing comparable
        self.assertTrue(report['warnings'])
        self.assertEqual(report['points_compared'], 0)

    def test_baseline_report_contract_shape(self):
        current = compare_lib._rows_to_map(make_rows(scale=0.88))
        report = compare_lib.compare_baseline(current, self._baseline(), tolerance_pct=5.0)
        self.assertEqual(
            set(report),
            {
                'schema_version',
                'mode',
                'tolerance_pct',
                'verdict',
                'findings',
                'warnings',
                'baseline_name',
                'improvements',
                'points_compared',
            },
        )
        self.assertTrue(report['findings'])
        for finding in report['findings']:
            self.assertEqual(
                set(finding),
                {'collective', 'size', 'dtype', 'in_place', 'bus_bw', 'baseline_bus_bw', 'deviation_pct'},
            )


class TestCompareScaling(unittest.TestCase):
    def _runs(self, scales):
        # scales: {node_count: scale_factor}
        return [(n, compare_lib._rows_to_map(make_rows(scale=s, nodes=n))) for n, s in scales.items()]

    def test_flat_curve_passes(self):
        report = compare_lib.compare_scaling(self._runs({2: 1.0, 4: 0.98, 8: 0.97}))
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['node_counts'], [2, 4, 8])

    def test_sagging_curve_flagged(self):
        report = compare_lib.compare_scaling(self._runs({2: 1.0, 4: 0.98, 8: 0.70}))
        self.assertEqual(report['verdict'], 'fail')
        self.assertTrue(all(f['node_count'] == 8 for f in report['findings']))
        f = report['findings'][0]
        self.assertEqual(f['reference_node_count'], 2)
        self.assertLess(f['deviation_pct'], -15.0)

    def test_unknown_collective_skipped(self):
        runs = self._runs({2: 1.0, 4: 1.0})
        # inject a non-flat-expectation collective into the 4-node run
        runs[1][1][('AllToAllV', 1048576, 'float', 0)] = 1.0
        report = compare_lib.compare_scaling(runs)
        self.assertEqual(report['verdict'], 'pass')

    def test_requires_two_runs(self):
        with self.assertRaises(ValueError):
            compare_lib.compare_scaling(self._runs({2: 1.0}))

    def test_duplicate_node_counts_raise(self):
        runs = self._runs({2: 1.0, 4: 1.0})
        runs.append((4, compare_lib._rows_to_map(make_rows(scale=0.99, nodes=4))))
        with self.assertRaises(ValueError):
            compare_lib.compare_scaling(runs)

    def test_key_missing_in_larger_run_warns(self):
        runs = self._runs({2: 1.0, 4: 1.0})
        del runs[1][1][('AllReduce', 1048576, 'float', 0)]
        report = compare_lib.compare_scaling(runs)
        self.assertTrue(any('4-node' in w for w in report['warnings']))
        self.assertEqual(report['verdict'], 'pass')

    def test_scaling_report_contract_shape(self):
        report = compare_lib.compare_scaling(self._runs({2: 1.0, 4: 0.98, 8: 0.70}))
        self.assertEqual(
            set(report),
            {
                'schema_version',
                'mode',
                'tolerance_pct',
                'verdict',
                'findings',
                'warnings',
                'node_counts',
                'points_compared',
            },
        )
        self.assertTrue(report['findings'])
        for finding in report['findings']:
            self.assertEqual(
                set(finding),
                {
                    'collective',
                    'size',
                    'dtype',
                    'in_place',
                    'node_count',
                    'bus_bw',
                    'reference_node_count',
                    'reference_bus_bw',
                    'deviation_pct',
                },
            )


if __name__ == '__main__':
    unittest.main()
