'''
cvs describe — machine-readable catalog of every cvs subcommand for agents/tools.

The discovery keystone of agent-operable CVS: one call returns the whole CLI
surface (args auto-derived from argparse, plus optional per-command semantics
from each plugin's describe()), so an agent can construct valid invocations
without reading source. Exit codes: 0 ok, 2 unknown --command/usage error.
'''

import argparse
import importlib.metadata
import re
import sys

import cvs.lib.validation_report as validation_report

from .base import SubcommandPlugin

SCHEMA_VERSION = 1


def _cvs_version():
    try:
        return importlib.metadata.version('cvs')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def _arg_descriptor(action):
    '''One argparse action -> a JSON-friendly argument descriptor.'''
    positional = not action.option_strings
    name = action.option_strings[0] if action.option_strings else action.dest
    # store_true/false/const consume no value; everything else takes one.
    takes_value = not isinstance(
        action,
        (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._StoreConstAction),
    )
    if positional:
        # Positionals carry no .required flag; they are required unless nargs
        # makes them optional ('?' or '*').
        required = action.nargs not in ('?', '*')
    else:
        required = bool(action.required)
    default = action.default
    if default is argparse.SUPPRESS:
        default = None
    full = {
        'name': name,
        'positional': positional,
        'required': required,
        'help': action.help or '',
        'choices': list(action.choices) if action.choices else None,
        'default': default,
        'takes_value': takes_value,
        'nargs': action.nargs,
    }
    # Drop keys at their "absent" value to keep the catalog small — an agent
    # parsing describe assumes these defaults when a key is missing.
    # ponytail: omission-as-default; if a consumer needs an explicit null, stop dropping that key.
    absent = {'positional': False, 'help': '', 'choices': None, 'default': None, 'takes_value': True, 'nargs': None}
    return {k: v for k, v in full.items() if k not in absent or absent[k] != v}


def describe_arguments(parser):
    '''Introspect an argparse subparser.

    Returns ``(arguments, subcommands)`` where *arguments* is a list of arg
    descriptors and *subcommands* maps each nested subcommand name to
    ``{"help", "arguments"}``. The -h/--help action is excluded.
    '''
    arguments = []
    subcommands = {}
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            help_map = {a.dest: (a.help or '') for a in action._choices_actions}
            for sub_name, sub_parser in action.choices.items():
                sub_args, _ = describe_arguments(sub_parser)
                subcommands[sub_name] = {'help': help_map.get(sub_name, ''), 'arguments': sub_args}
            continue
        arguments.append(_arg_descriptor(action))
    return arguments, subcommands


def _epilog_examples(plugin):
    '''Pull ``cvs ...`` invocation lines out of a plugin's epilog text.'''
    examples = []
    for line in (plugin.get_epilog() or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('cvs '):
            # Epilogs align a description after 2+ spaces; keep only the command.
            examples.append(re.split(r'\s{2,}', stripped)[0].strip())
    return examples


def build_command(plugin):
    '''Build one command descriptor by merging argparse introspection with the
    plugin's optional describe() metadata.'''
    name = plugin.get_name()
    # Register the plugin into a throwaway parser to read its argparse surface
    # without affecting the real CLI.
    holder = argparse.ArgumentParser(add_help=False)
    sub = holder.add_subparsers()
    plugin.get_parser(sub)
    sub_help = {a.dest: (a.help or '') for a in sub._choices_actions}
    subparser = sub.choices.get(name)
    arguments, subcommands = describe_arguments(subparser) if subparser is not None else ([], {})

    try:
        meta = plugin.describe() or {}
    except Exception:
        meta = {}

    command = {
        'name': name,
        'summary': meta.get('summary') or sub_help.get(name, '') or '',
        'read_only': meta.get('read_only', None),
        'exit_codes': meta.get('exit_codes', {}),
        'arguments': arguments,
        'input_files': meta.get('input_files', []),
        'examples': meta.get('examples') or _epilog_examples(plugin),
    }
    if meta.get('output'):
        command['output'] = meta['output']
    if subcommands:
        command['subcommands'] = subcommands
    return command


def build_catalog(plugins=None):
    '''Assemble the full catalog. *plugins* defaults to the real discovered set.'''
    if plugins is None:
        from cvs.main import discover_plugins  # lazy: avoids import cycle at load

        plugins = discover_plugins()
    commands = sorted((build_command(p) for p in plugins), key=lambda c: c['name'])
    return {
        'schema_version': SCHEMA_VERSION,
        'cvs_version': _cvs_version(),
        'response_contract': validation_report.RESPONSE_CONTRACT,
        'commands': commands,
    }


def render_table(catalog):
    '''Human-readable rendering of the catalog.'''
    lines = [f"cvs {catalog['cvs_version']} — {len(catalog['commands'])} commands"]
    for cmd in catalog['commands']:
        flag = ' [read-only]' if cmd.get('read_only') else ''
        lines.append(f"  {cmd['name']}{flag}  {cmd['summary']}".rstrip())
        for arg in cmd.get('arguments', []):
            req = 'required' if arg.get('required') else 'optional'
            choices = f" {{{','.join(arg['choices'])}}}" if arg.get('choices') else ''
            lines.append(f"      {arg['name']}{choices} ({req})")
        for sub_name in cmd.get('subcommands', {}):
            lines.append(f"      <{sub_name}>")
    return '\n'.join(lines)


class DescribePlugin(SubcommandPlugin):
    def get_name(self):
        return 'describe'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser(
            'describe', help='Machine-readable catalog of all cvs commands (for agents/tools)'
        )
        parser.set_defaults(_plugin=self)
        parser.add_argument('--format', choices=('json', 'table'), default='json')
        parser.add_argument('--command', default=None, help='Describe only this command')
        parser.add_argument(
            '--brief',
            action='store_true',
            help='Names + one-line summaries only (cheap cold-start scan; drill in with --command)',
        )
        return parser

    def describe(self):
        return {
            'summary': 'Self-describing catalog of every cvs subcommand for agents and tooling.',
            'read_only': True,
            'exit_codes': {'0': 'ok', '2': 'unknown --command or usage error'},
            'examples': ['cvs describe --format json', 'cvs describe --command preflight'],
        }

    def run(self, args):
        catalog = build_catalog()
        if args.command:
            matches = [c for c in catalog['commands'] if c['name'] == args.command]
            if not matches:
                validation_report.emit_error(
                    f'unknown command {args.command!r}', args.format, hint='run "cvs describe" to list commands'
                )
            catalog = {**catalog, 'commands': matches}
        if getattr(args, 'brief', False):
            brief = [
                {'name': c['name'], 'summary': c['summary'], 'read_only': c['read_only']} for c in catalog['commands']
            ]
            catalog = {**catalog, 'commands': brief}
        if args.format == 'json':
            import json

            print(json.dumps(catalog, indent=2))
        else:
            print(render_table(catalog))
        sys.exit(0)
