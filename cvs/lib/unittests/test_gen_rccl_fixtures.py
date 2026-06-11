import unittest

from cvs.lib.unittests.fixtures.gen_rccl_fixtures import make_rows
from cvs.schema.rccl import RcclTestsAggregated


class TestMakeRows(unittest.TestCase):
    def test_rows_validate_against_schema(self):
        rows = make_rows()
        self.assertGreater(len(rows), 0)
        for row in rows:
            RcclTestsAggregated.model_validate(row)  # raises on mismatch

    def test_default_grid(self):
        # 2 collectives x 3 sizes x 1 dtype x 1 inPlace = 6 rows
        rows = make_rows()
        self.assertEqual(len(rows), 6)

    def test_scale_factor_applies_to_bus_bw(self):
        base = {r['size']: r['busBw_mean'] for r in make_rows() if r['name'] == 'AllReduce'}
        scaled = {r['size']: r['busBw_mean'] for r in make_rows(scale=0.9) if r['name'] == 'AllReduce'}
        for size, bw in base.items():
            self.assertAlmostEqual(scaled[size], bw * 0.9, places=4)

    def test_scale_only_selected_collective(self):
        rows = make_rows(scale=0.8, only_collective='AllGather')
        base = {(r['name'], r['size']): r['busBw_mean'] for r in make_rows()}
        for row in rows:
            base_bw = base[(row['name'], row['size'])]
            if row['name'] == 'AllGather':
                self.assertAlmostEqual(row['busBw_mean'], base_bw * 0.8, places=4)
            else:
                self.assertEqual(row['busBw_mean'], base_bw)


if __name__ == '__main__':
    unittest.main()
