import json
import tempfile
import unittest
from pathlib import Path

import cvs.lib.input_validation_lib as iv


CONTRACT = [
    {'arg': '--cluster_file', 'format': 'json', 'required_keys': ['node_dict'], 'optional_keys': ['username']},
    {'arg': '--config_file', 'format': 'json', 'required_keys': [], 'optional_keys': ['rccl']},
]


class TestValidateInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, text):
        p = Path(self.tmp.name) / name
        p.write_text(text)
        return str(p)

    def test_valid_file_passes(self):
        good = self._write('cluster.json', json.dumps({'node_dict': {'10.0.0.1': {}}, 'username': 'amd'}))
        report = iv.validate_inputs(CONTRACT, {'--cluster_file': good})
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['mode'], 'validate')
        self.assertEqual(report['schema_version'], iv.SCHEMA_VERSION)

    def test_missing_required_key_fails(self):
        bad = self._write('cluster.json', json.dumps({'username': 'amd'}))
        report = iv.validate_inputs(CONTRACT, {'--cluster_file': bad})
        self.assertEqual(report['verdict'], 'fail')
        issues = ' '.join(f['issue'] for f in report['findings'])
        self.assertIn('node_dict', issues)
        # findings share a uniform key set so validation_report can tabulate them.
        self.assertEqual(set(report['findings'][0]), {'file', 'arg', 'issue'})

    def test_missing_file_fails(self):
        report = iv.validate_inputs(CONTRACT, {'--cluster_file': '/no/such/cluster.json'})
        self.assertEqual(report['verdict'], 'fail')
        self.assertIn('not found', report['findings'][0]['issue'])

    def test_invalid_json_fails(self):
        bad = self._write('cluster.json', '{not json')
        report = iv.validate_inputs(CONTRACT, {'--cluster_file': bad})
        self.assertEqual(report['verdict'], 'fail')
        self.assertIn('JSON', report['findings'][0]['issue'])

    def test_non_object_toplevel_fails(self):
        bad = self._write('cluster.json', json.dumps(['not', 'an', 'object']))
        report = iv.validate_inputs(CONTRACT, {'--cluster_file': bad})
        self.assertEqual(report['verdict'], 'fail')
        self.assertIn('object', report['findings'][0]['issue'])

    def test_unprovided_file_warns_not_fails(self):
        # A command may take an optional config file; not supplying it is a
        # warning, not a validation failure.
        good = self._write('cluster.json', json.dumps({'node_dict': {'10.0.0.1': {}}}))
        report = iv.validate_inputs(CONTRACT, {'--cluster_file': good, '--config_file': None})
        self.assertEqual(report['verdict'], 'pass')
        self.assertTrue(any('--config_file' in w for w in report['warnings']))

    def test_empty_contract_passes(self):
        report = iv.validate_inputs([], {})
        self.assertEqual(report['verdict'], 'pass')


if __name__ == '__main__':
    unittest.main()
