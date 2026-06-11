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
            {'schema_version', 'mode', 'tolerance_pct', 'verdict',
             'findings', 'warnings', 'nodes', 'points_compared'},
        )
        self.assertTrue(report['findings'])
        for finding in report['findings']:
            self.assertEqual(
                set(finding),
                {'node', 'collective', 'size', 'dtype', 'in_place',
                 'bus_bw', 'fleet_median', 'deviation_pct'},
            )

    def test_fewer_than_three_nodes_skips_with_warning(self):
        report = compare_lib.compare_peers(self._fleet(n=2))
        self.assertEqual(report['verdict'], 'pass')
        self.assertTrue(any('need >= 3' in w for w in report['warnings']))


if __name__ == '__main__':
    unittest.main()
