'''
JSON Schemas for cvs input files (cluster_file, config_file). A published,
machine-consumable contract an agent or editor can validate against or use to
generate inputs. The required keys mirror what `cvs describe` declares so the
two stay consistent. Pure data + lookup.
'''

_DRAFT = 'https://json-schema.org/draft/2020-12/schema'

CLUSTER_FILE_SCHEMA = {
    '$schema': _DRAFT,
    'title': 'CVS cluster file',
    'description': 'Describes the cluster testbed: nodes, SSH credentials, and per-command env.',
    'type': 'object',
    'required': ['node_dict'],
    'properties': {
        'username': {'type': 'string', 'description': 'SSH username for all nodes'},
        'priv_key_file': {
            'type': 'string',
            'description': 'Path to the SSH private key; omit to fall back to ssh-agent',
        },
        'env_vars': {'type': 'object', 'description': 'Env vars exported before each remote command'},
        'head_node_dict': {
            'type': 'object',
            'description': 'Head/management node info',
            'properties': {'mgmt_ip': {'type': 'string'}},
        },
        'node_dict': {
            'type': 'object',
            'description': 'Map of node IP/hostname -> per-node metadata',
            'minProperties': 1,
            'additionalProperties': {
                'type': 'object',
                'properties': {
                    'bmc_ip': {'type': 'string'},
                    'vpc_ip': {'type': 'string', 'description': 'cluster-internal IP, or same as the host IP'},
                },
            },
        },
    },
}

CONFIG_FILE_SCHEMA = {
    '$schema': _DRAFT,
    'title': 'CVS config file (rccl)',
    'description': 'Test parameters and paths. Keys cvs reads live under "rccl".',
    'type': 'object',
    'properties': {
        'rccl': {
            'type': 'object',
            'properties': {
                'mpi_params': {
                    'type': 'object',
                    'properties': {'mpi_dir': {'type': 'string', 'description': 'mpirun bin dir'}},
                },
                'rccl_test_params': {
                    'type': 'object',
                    'properties': {'rccl_tests_dir': {'type': 'string', 'description': 'rccl-tests build dir'}},
                },
                'cvs_params': {
                    'type': 'object',
                    'properties': {'nic_model': {'type': 'string', 'description': "e.g. 'thor', 'connectx'"}},
                },
                'env_source_script': {'type': 'string', 'description': 'Path to a shell env script sourced per run'},
            },
        },
    },
}

_SCHEMAS = {'cluster_file': CLUSTER_FILE_SCHEMA, 'config_file': CONFIG_FILE_SCHEMA}


def available():
    '''Sorted list of schema kinds.'''
    return sorted(_SCHEMAS)


def get_schema(kind):
    '''Return the JSON Schema dict for *kind*; raise ValueError if unknown.'''
    if kind not in _SCHEMAS:
        raise ValueError(f'unknown schema {kind!r}; choices: {available()}')
    return _SCHEMAS[kind]
