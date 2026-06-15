import argparse
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from cvs.cli_plugins.base import SubcommandPlugin
from cvs.cli_plugins.preflight_plugin import PreflightPlugin
from cvs.cli_plugins.run_plugin import RunPlugin
from cvs.cli_plugins import describe_plugin
from cvs.cli_plugins.describe_plugin import DescribePlugin


def _subparser_for(plugin):
    """Register *plugin* into a throwaway parser and return its subparser."""
    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers()
    plugin.get_parser(sub)
    return sub.choices[plugin.get_name()]


class TestBaseDescribeDefault(unittest.TestCase):
    def test_base_describe_defaults_to_empty(self):
        # Every plugin inherits an optional describe() returning {} so the
        # catalog builder can call it unconditionally.
        self.assertEqual(SubcommandPlugin().describe(), {})


class TestDescribeArguments(unittest.TestCase):
    def test_maps_preflight_arguments(self):
        args, subcommands = describe_plugin.describe_arguments(_subparser_for(PreflightPlugin()))
        by_name = {a['name']: a for a in args}
        self.assertIn('--cluster_file', by_name)
        self.assertTrue(by_name['--cluster_file']['required'])
        self.assertTrue(by_name['--cluster_file']['takes_value'])
        # --format carries argparse choices an agent can pick from.
        self.assertIn('--format', by_name)
        self.assertIsNotNone(by_name['--format']['choices'])
        self.assertIn('json', by_name['--format']['choices'])
        self.assertEqual(by_name['--format']['default'], 'table')
        # preflight has no nested subcommands.
        self.assertEqual(subcommands, {})

    def test_help_action_is_excluded(self):
        # add_help defaults True on argparse parsers; the -h/--help action
        # must never leak into the described argument set.
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        PreflightPlugin().get_parser(sub)
        args, _ = describe_plugin.describe_arguments(sub.choices['preflight'])
        self.assertNotIn('-h', [a['name'] for a in args])

    def test_captures_nested_subcommands(self):
        # baseline uses a nested subparser (capture/list/show/delete); those
        # must surface so an agent can see capture needs --name.
        from cvs.cli_plugins.baseline_plugin import BaselinePlugin

        _, subcommands = describe_plugin.describe_arguments(_subparser_for(BaselinePlugin()))
        self.assertIn('capture', subcommands)
        capture_args = {a['name'] for a in subcommands['capture']['arguments']}
        self.assertIn('--name', capture_args)


class TestBuildCatalog(unittest.TestCase):
    def test_catalog_shape(self):
        catalog = describe_plugin.build_catalog(plugins=[PreflightPlugin(), RunPlugin()])
        self.assertEqual(catalog['schema_version'], describe_plugin.SCHEMA_VERSION)
        self.assertIn('cvs_version', catalog)
        names = [c['name'] for c in catalog['commands']]
        self.assertEqual(names, sorted(names))
        self.assertEqual(set(names), {'preflight', 'run'})
        for cmd in catalog['commands']:
            self.assertIn('arguments', cmd)
            self.assertIsInstance(cmd['arguments'], list)

    def test_engine_command_surfaces_semantics(self):
        catalog = describe_plugin.build_catalog(plugins=[PreflightPlugin()])
        cmd = catalog['commands'][0]
        self.assertTrue(cmd['read_only'])
        self.assertEqual(cmd['exit_codes']['1'], 'checks failed')
        input_args = {f['arg'] for f in cmd['input_files']}
        self.assertIn('--cluster_file', input_args)
        cluster = next(f for f in cmd['input_files'] if f['arg'] == '--cluster_file')
        self.assertIn('node_dict', cluster['required_keys'])

    def test_upstream_command_degrades_gracefully(self):
        # run has no describe(); it must still produce a full arg listing with
        # defaulted semantic fields and never raise.
        catalog = describe_plugin.build_catalog(plugins=[RunPlugin()])
        cmd = catalog['commands'][0]
        self.assertIsNone(cmd['read_only'])
        self.assertEqual(cmd['exit_codes'], {})
        self.assertEqual(cmd['input_files'], [])
        arg_names = {a['name'] for a in cmd['arguments']}
        self.assertIn('--cluster_file', arg_names)
        self.assertIn('--config_file', arg_names)

    def test_catalog_is_json_serializable(self):
        catalog = describe_plugin.build_catalog(plugins=[PreflightPlugin(), RunPlugin()])
        json.loads(json.dumps(catalog))  # must not raise


class TestDescribePluginRun(unittest.TestCase):
    def setUp(self):
        self.plugin = DescribePlugin()
        parser = argparse.ArgumentParser()
        self.plugin.get_parser(parser.add_subparsers(dest='command'))
        self.parser = parser

    def _run(self, argv):
        args = self.parser.parse_args(argv)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                self.plugin.run(args)
        return ctx.exception.code, out.getvalue(), err.getvalue()

    def test_json_default_lists_all_real_commands(self):
        code, out, _ = self._run(['describe'])
        self.assertEqual(code, 0)
        catalog = json.loads(out)
        names = {c['name'] for c in catalog['commands']}
        # discovery sees the real installed plugin set, including itself.
        self.assertIn('describe', names)
        self.assertIn('preflight', names)

    def test_command_filter(self):
        code, out, _ = self._run(['describe', '--command', 'preflight'])
        self.assertEqual(code, 0)
        catalog = json.loads(out)
        self.assertEqual([c['name'] for c in catalog['commands']], ['preflight'])

    def test_unknown_command_exits_2(self):
        code, _, err = self._run(['describe', '--command', 'nope'])
        self.assertEqual(code, 2)
        self.assertIn('nope', err)

    def test_table_format_renders(self):
        code, out, _ = self._run(['describe', '--format', 'table'])
        self.assertEqual(code, 0)
        self.assertIn('preflight', out)


if __name__ == '__main__':
    unittest.main()
