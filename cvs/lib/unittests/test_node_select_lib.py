import unittest

import cvs.lib.node_select_lib as ns


ALL = ['10.0.0.1', '10.0.0.2', '10.0.0.3']


class TestSelectNodes(unittest.TestCase):
    def test_none_returns_all(self):
        self.assertEqual(ns.select_nodes(ALL, None), ALL)

    def test_empty_returns_all(self):
        self.assertEqual(ns.select_nodes(ALL, ''), ALL)

    def test_subset_preserves_cluster_order(self):
        # requested out of order -> result still follows the cluster's order
        self.assertEqual(ns.select_nodes(ALL, '10.0.0.3,10.0.0.1'), ['10.0.0.1', '10.0.0.3'])

    def test_whitespace_and_dedup(self):
        self.assertEqual(ns.select_nodes(ALL, ' 10.0.0.2 , 10.0.0.2 '), ['10.0.0.2'])

    def test_unknown_node_raises(self):
        with self.assertRaises(ValueError) as ctx:
            ns.select_nodes(ALL, '10.0.0.9')
        self.assertIn('10.0.0.9', str(ctx.exception))

    def test_returns_new_list(self):
        result = ns.select_nodes(ALL, None)
        result.append('x')
        self.assertEqual(len(ALL), 3)  # original untouched


if __name__ == '__main__':
    unittest.main()
