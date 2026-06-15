'''
cvs schema — emit the JSON Schema for a cvs input file (cluster_file or
config_file), so an agent or editor can validate inputs rigorously or generate
them. Exit codes: 0 ok, 2 usage error (argparse rejects an unknown kind).
'''

import json
import sys

import cvs.lib.input_schema_lib as input_schema_lib

from .base import SubcommandPlugin


class SchemaPlugin(SubcommandPlugin):
    def get_name(self):
        return 'schema'

    def get_parser(self, subparsers):
        parser = subparsers.add_parser('schema', help='Print the JSON Schema for a cvs input file')
        parser.set_defaults(_plugin=self)
        parser.add_argument('kind', choices=input_schema_lib.available(), help='Which input file to describe')
        return parser

    def describe(self):
        return {
            'summary': 'Print the JSON Schema for a cvs input file (cluster_file or config_file).',
            'read_only': True,
            'exit_codes': {'0': 'ok', '2': 'unknown kind or usage error'},
            'examples': ['cvs schema cluster_file', 'cvs schema config_file'],
        }

    def run(self, args):
        print(json.dumps(input_schema_lib.get_schema(args.kind), indent=2))
        sys.exit(0)
