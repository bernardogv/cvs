import json
import unittest

import cvs.lib.input_schema_lib as schema


class TestInputSchemaLib(unittest.TestCase):
    def test_available_lists_both_kinds(self):
        self.assertEqual(schema.available(), ['cluster_file', 'config_file'])

    def test_cluster_file_schema_requires_node_dict(self):
        s = schema.get_schema('cluster_file')
        self.assertEqual(s['type'], 'object')
        self.assertIn('node_dict', s['required'])
        self.assertIn('$schema', s)
        # node_dict is a non-empty map of node -> metadata
        node_dict = s['properties']['node_dict']
        self.assertEqual(node_dict['type'], 'object')
        self.assertEqual(node_dict['minProperties'], 1)

    def test_cluster_file_schema_matches_describe_contract(self):
        # The schema's required keys must agree with preflight's declared
        # input_files contract (single source of truth via describe).
        from cvs.cli_plugins.preflight_plugin import PreflightPlugin

        declared = next(f for f in PreflightPlugin().describe()['input_files'] if f['arg'] == '--cluster_file')[
            'required_keys'
        ]
        self.assertEqual(set(schema.get_schema('cluster_file')['required']), set(declared))

    def test_config_file_schema_exposes_rccl(self):
        s = schema.get_schema('config_file')
        self.assertIn('rccl', s['properties'])

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError) as ctx:
            schema.get_schema('nope')
        self.assertIn('nope', str(ctx.exception))

    def test_schemas_are_json_serializable(self):
        for kind in schema.available():
            json.loads(json.dumps(schema.get_schema(kind)))


if __name__ == '__main__':
    unittest.main()
