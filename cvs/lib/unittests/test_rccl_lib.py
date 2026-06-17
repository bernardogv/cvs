# cvs/lib/unittests/test_rccl_lib.py
import unittest
from unittest.mock import patch
import cvs.lib.rccl_lib as rccl_lib


class TestRcclLib(unittest.TestCase):
    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_avg_bus_bw_success(self, mock_fail_test):
        output = "# Avg bus bandwidth : 100.5"
        exp_res_dict = {'avg_bus_bw': 100.0}
        rccl_lib.check_avg_bus_bw(output, exp_res_dict)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_avg_bus_bw_failure(self, mock_fail_test):
        output = "# Avg bus bandwidth : 90.0"
        exp_res_dict = {'avg_bus_bw': 100.0}
        rccl_lib.check_avg_bus_bw(output, exp_res_dict)
        mock_fail_test.assert_called_once()

    def test_check_avg_bus_bw_no_match(self):
        output = "No bandwidth info"
        exp_res_dict = {'avg_bus_bw': 100.0}
        # Should not raise or fail
        rccl_lib.check_avg_bus_bw(output, exp_res_dict)

    def test_convert_to_graph_dict(self):
        # Test with sample data
        result_dict = {
            'allreduce': [{'size': 1024, 'name': 'allreduce', 'inPlace': 0, 'busBw': 100.0, 'algBw': 90.0, 'time': 1.0}]
        }
        result = rccl_lib.convert_to_graph_dict(result_dict)
        self.assertIsInstance(result, dict)

    # Tests for new verification functions

    def test_is_severe_wrong_corruption_error(self):
        """Test severe corruption error detection"""

        # Test with actual ValidationError-like object for structured errors
        class MockValidationError:
            def errors(self):
                return [{'msg': 'SEVERE DATA CORRUPTION detected'}]

            def __str__(self):
                return "ValidationError with SEVERE DATA CORRUPTION"

        mock_error = MockValidationError()
        self.assertTrue(rccl_lib._is_severe_wrong_corruption_error(mock_error))

        # Test with '#wrong' pattern
        class MockWrongError:
            def errors(self):
                return [{'msg': "Field validation failed: '#wrong' > 0"}]

            def __str__(self):
                return "ValidationError with wrong"

        mock_error = MockWrongError()
        self.assertTrue(rccl_lib._is_severe_wrong_corruption_error(mock_error))

        # Test fallback to string search with '#wrong' pattern
        class MockStringError:
            def errors(self):
                raise Exception("No structured errors")

            def __str__(self):
                return "ValidationError contains '#wrong' > 0"

        mock_error = MockStringError()
        self.assertTrue(rccl_lib._is_severe_wrong_corruption_error(mock_error))

        # Test normal error (should not be severe)
        class MockNormalError:
            def errors(self):
                raise Exception("No structured errors")

            def __str__(self):
                return "Normal validation error"

        mock_error = MockNormalError()
        self.assertFalse(rccl_lib._is_severe_wrong_corruption_error(mock_error))

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_scan_rccl_logs_success(self, mock_fail_test):
        """Test successful log scanning"""
        output = """
        INFO: Test starting
        NCCL WARN: Performance warning
        # Avg bus bandwidth    :   85.5
        Test completed successfully
        """

        rccl_lib.scan_rccl_logs(output)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_scan_rccl_logs_orte_error(self, mock_fail_test):
        """Test log scanning with ORTE error"""
        output = """
        INFO: Test starting
        ORTE does not know how to route to destination
        """

        rccl_lib.scan_rccl_logs(output)
        mock_fail_test.assert_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_scan_rccl_logs_nccl_error(self, mock_fail_test):
        """Test log scanning with NCCL error"""
        output = """
        INFO: Test starting
        NCCL ERROR: Something went wrong
        """

        rccl_lib.scan_rccl_logs(output)
        mock_fail_test.assert_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_scan_rccl_logs_missing_bandwidth(self, mock_fail_test):
        """Test log scanning without bandwidth marker"""
        output = """
        INFO: Test starting
        Test completed but no bandwidth printed
        """

        rccl_lib.scan_rccl_logs(output)
        mock_fail_test.assert_called_with(
            'RCCL test did not complete successfully, no bandwidth numbers printed - pls check'
        )

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_bus_bw_success(self, mock_fail_test):
        """Test successful bus bandwidth validation"""
        test_name = "all_reduce_perf"
        output = [
            {
                "name": "all_reduce_perf",
                "size": 1024,
                "type": "float",
                "inPlace": 1,
                "busBw": 90.0,
                "algBw": 45.0,
                "time": 12.3,
            }
        ]
        exp_res_dict = {"1024": {"bus_bw": 80.0}}

        rccl_lib.check_bus_bw(test_name, output, exp_res_dict)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_bus_bw_failure(self, mock_fail_test):
        """Test bus bandwidth validation failure"""
        test_name = "all_reduce_perf"
        output = [
            {
                "name": "all_reduce_perf",
                "size": 1024,
                "type": "float",
                "inPlace": 1,
                "busBw": 70.0,  # Below threshold
                "algBw": 35.0,
                "time": 12.3,
            }
        ]
        exp_res_dict = {
            "1024": {"bus_bw": 80.0}  # 95% threshold would be 76.0
        }

        rccl_lib.check_bus_bw(test_name, output, exp_res_dict)
        mock_fail_test.assert_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_bus_bw_alltoall(self, mock_fail_test):
        """Test bus bandwidth validation for alltoall (out-of-place)"""
        test_name = "alltoall"
        output = [
            {
                "name": "alltoall",
                "size": 1024,
                "type": "float",
                "inPlace": 0,  # Out-of-place for alltoall
                "busBw": 90.0,
                "algBw": 45.0,
                "time": 12.3,
            }
        ]
        exp_res_dict = {"1024": {"bus_bw": 80.0}}

        rccl_lib.check_bus_bw(test_name, output, exp_res_dict)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_bw_dip_success(self, mock_fail_test):
        """Test successful bandwidth dip validation"""
        test_name = "all_reduce_perf"
        output = [
            {"size": 1024, "inPlace": 1, "busBw": 80.0},
            {"size": 2048, "inPlace": 1, "busBw": 85.0},  # Increasing BW
            {"size": 4096, "inPlace": 1, "busBw": 90.0},  # Still increasing
        ]
        exp_res_dict = {"1024": {"bus_bw": 75.0}, "2048": {"bus_bw": 80.0}, "4096": {"bus_bw": 85.0}}

        rccl_lib.check_bw_dip(test_name, output, exp_res_dict)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_bw_dip_failure(self, mock_fail_test):
        """Test bandwidth dip detection failure"""
        test_name = "all_reduce_perf"
        output = [
            {"size": 1024, "inPlace": 1, "busBw": 100.0},
            {"size": 2048, "inPlace": 1, "busBw": 90.0},  # Significant drop
        ]
        exp_res_dict = {"1024": {"bus_bw": 95.0}, "2048": {"bus_bw": 85.0}}

        rccl_lib.check_bw_dip(test_name, output, exp_res_dict)
        mock_fail_test.assert_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_bw_dip_no_reference(self, mock_fail_test):
        """Test bandwidth dip check without reference data"""
        test_name = "all_reduce_perf"
        output = [
            {"size": 1024, "inPlace": 1, "busBw": 100.0},
            {"size": 2048, "inPlace": 1, "busBw": 50.0},  # Big drop but no reference
        ]

        rccl_lib.check_bw_dip(test_name, output, None)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_lat_dip_success(self, mock_fail_test):
        """Test successful latency dip validation"""
        test_name = "all_reduce_perf"
        output = [
            {"size": 1024, "inPlace": 1, "time": 10.0},
            {"size": 2048, "inPlace": 1, "time": 15.0},  # Increasing latency (normal)
            {"size": 4096, "inPlace": 1, "time": 20.0},  # Still increasing
        ]
        exp_res_dict = {"1024": {"bus_bw": 75.0}, "2048": {"bus_bw": 80.0}, "4096": {"bus_bw": 85.0}}

        rccl_lib.check_lat_dip(test_name, output, exp_res_dict)
        mock_fail_test.assert_not_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_lat_dip_failure(self, mock_fail_test):
        """Test latency dip detection failure"""
        test_name = "all_reduce_perf"
        output = [
            {"size": 1024, "inPlace": 1, "time": 20.0},
            {"size": 2048, "inPlace": 1, "time": 15.0},  # Unexpected latency decrease
        ]
        exp_res_dict = {"1024": {"bus_bw": 95.0}, "2048": {"bus_bw": 85.0}}

        rccl_lib.check_lat_dip(test_name, output, exp_res_dict)
        mock_fail_test.assert_called()

    @patch('cvs.lib.rccl_lib.fail_test')
    def test_check_lat_dip_no_reference(self, mock_fail_test):
        """Test latency dip check without reference data"""
        test_name = "all_reduce_perf"
        output = [
            {"size": 1024, "inPlace": 1, "time": 20.0},
            {"size": 2048, "inPlace": 1, "time": 5.0},  # Big drop but no reference
        ]

        rccl_lib.check_lat_dip(test_name, output, None)
        mock_fail_test.assert_not_called()


class TestDetermineMpiPmlConfig(unittest.TestCase):
    """determine_mpi_pml_config builds the mpirun --mca pml flag and UCX env.

    UCX env is built piecewise: UCX_UNIFIED_MODE whenever UCX is active,
    UCX_NET_DEVICES only when a device list is configured, and UCX_TLS only for
    a concrete transport (not auto/none/tcp/empty).
    """

    def _call(self, mpi_pml, net_dev_list, ucx_tls):
        # shdl/mpi_path/head_node are only used by the auto/ob1-detect path.
        return rccl_lib.determine_mpi_pml_config(mpi_pml, None, None, None, net_dev_list, ucx_tls)

    def test_ucx_concrete_tls_emits_all_three(self):
        pml, ucx = self._call("ucx", "mlx5_0:1", "rc")
        self.assertEqual(pml, "--mca pml ucx")
        self.assertIn("UCX_UNIFIED_MODE=y", ucx)
        self.assertIn("UCX_NET_DEVICES=mlx5_0:1", ucx)
        self.assertIn("UCX_TLS=rc", ucx)

    def test_ucx_tls_auto_is_not_pinned_but_devices_kept(self):
        pml, ucx = self._call("ucx", "mlx5_0:1", "auto")
        self.assertEqual(pml, "--mca pml ucx")
        self.assertIn("UCX_UNIFIED_MODE=y", ucx)
        self.assertIn("UCX_NET_DEVICES=mlx5_0:1", ucx)
        self.assertNotIn("UCX_TLS", ucx)

    def test_ucx_tls_tcp_default_is_not_pinned(self):
        # 'tcp' is the caller default; pinning it forces the slow TCP path.
        _, ucx = self._call("ucx", "mlx5_0:1", "tcp")
        self.assertNotIn("UCX_TLS", ucx)
        self.assertIn("UCX_NET_DEVICES=mlx5_0:1", ucx)

    def test_empty_net_dev_list_emits_no_device_pin(self):
        # An empty UCX_NET_DEVICES= pin is itself broken; omit it.
        _, ucx = self._call("ucx", "", "auto")
        self.assertIn("UCX_UNIFIED_MODE=y", ucx)
        self.assertNotIn("UCX_NET_DEVICES", ucx)

    def test_ob1_has_no_ucx_env(self):
        pml, ucx = self._call("ob1", "mlx5_0:1", "rc")
        self.assertEqual(pml, "--mca pml ob1")
        self.assertEqual(ucx, "")

    @patch("cvs.lib.rccl_lib.is_ucx_available_in_mpi", return_value=True)
    def test_auto_with_ucx_available_builds_ucx_env(self, _mock_avail):
        pml, ucx = self._call("auto", "mlx5_0:1", "rc")
        self.assertEqual(pml, "")  # auto leaves pml unset when UCX is available
        self.assertIn("UCX_NET_DEVICES=mlx5_0:1", ucx)
        self.assertIn("UCX_TLS=rc", ucx)

    @patch("cvs.lib.rccl_lib.is_ucx_available_in_mpi", return_value=False)
    def test_auto_without_ucx_falls_back_to_ob1(self, _mock_avail):
        pml, ucx = self._call("auto", "mlx5_0:1", "rc")
        self.assertEqual(pml, "--mca pml ob1")
        self.assertEqual(ucx, "")


class TestBuildMpirunCmd(unittest.TestCase):
    """The shared mpirun envelope used by both rccl_perf and rccl_regression."""

    def _cmd(self, **kw):
        defaults = dict(
            mpi_dir='/home/u/openmpi',
            no_of_global_ranks=16,
            ucx_params='-x UCX_UNIFIED_MODE=y -x UCX_NET_DEVICES=mlx5_0:1 ',
            mpi_oob_port='eth0',
            pml_param='--mca pml ucx',
            test_cmd='bash -c "RCCL_BINARY"',
        )
        defaults.update(kw)
        return rccl_lib.build_mpirun_cmd(**defaults)

    def test_contains_the_mpi_envelope(self):
        cmd = ' '.join(self._cmd().split())  # collapse whitespace like the shell does
        for token in (
            '/home/u/openmpi/bin/mpirun',
            '--allow-run-as-root',
            '-np 16',
            '--hostfile /tmp/rccl_hosts_file.txt',
            '--bind-to numa',
            '-x UCX_NET_DEVICES=mlx5_0:1',
            '--mca btl ^vader,openib',
            '--mca btl_tcp_if_include eth0',
            '--mca oob_tcp_if_include eth0',
            '--mca pml ucx',
        ):
            self.assertIn(token, cmd)

    def test_test_cmd_is_last(self):
        cmd = ' '.join(self._cmd().split())
        self.assertTrue(cmd.rstrip().endswith('bash -c "RCCL_BINARY"'))

    def test_env_override_included_when_given(self):
        cmd = ' '.join(self._cmd(env_override_params='-x NCCL_ALGO=Ring').split())
        self.assertIn('-x NCCL_ALGO=Ring', cmd)

    def test_env_override_absent_by_default(self):
        self.assertNotIn('NCCL_', ' '.join(self._cmd().split()))

    def test_perf_and_regression_share_one_envelope(self):
        # Same inputs -> byte-identical command, regardless of caller. This is
        # the whole point: the two paths can no longer drift in the MPI flags.
        perf = self._cmd(test_cmd='T')
        regr = rccl_lib.build_mpirun_cmd(
            '/home/u/openmpi',
            16,
            '-x UCX_UNIFIED_MODE=y -x UCX_NET_DEVICES=mlx5_0:1 ',
            'eth0',
            '--mca pml ucx',
            'T',
        )
        self.assertEqual(perf, regr)


if __name__ == '__main__':
    unittest.main()
