'''
Guard the shipped rccl config sample against the mpi_dir path-convention bug:
the launcher (rccl_lib) and preflight both build {mpi_dir}/bin/mpirun, so
mpi_dir must be the Open MPI *root*, not .../bin (which would double the bin
segment and break mpirun discovery for anyone copying the template).
'''

import json
import unittest
from pathlib import Path

import cvs

RCCL_CONFIG = Path(cvs.__file__).parent / 'input' / 'config_file' / 'rccl' / 'rccl_config.json'


class TestRcclConfigSample(unittest.TestCase):
    def test_mpi_dir_is_root_not_bin(self):
        mpi_dir = json.loads(RCCL_CONFIG.read_text())['rccl']['mpi_params']['mpi_dir']
        # The launcher appends '/bin/mpirun'; a trailing '/bin' here yields
        # '.../bin/bin/mpirun'.
        self.assertFalse(
            mpi_dir.rstrip('/').endswith('/bin'),
            f'mpi_dir must be the Open MPI root (launcher appends /bin/mpirun); got {mpi_dir!r}',
        )


if __name__ == '__main__':
    unittest.main()
