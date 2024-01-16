from queue import Queue, Full
from unittest import TestCase
from unittest.mock import Mock, patch

from nuvlaedge.agent.workers.monitor.data.nuvlaedge_data import NuvlaEdgeData
from nuvlaedge.agent.nuvla.resources.nuvla_id import NuvlaID
from nuvlaedge.agent.workers.telemetry import Telemetry, model_diff, TelemetryPayloadAttributes
from nuvlaedge.agent.orchestrator import COEClient


def test_model_diff():
    model_1 = TelemetryPayloadAttributes()
    model_2 = TelemetryPayloadAttributes()

    assert model_diff(model_1, model_2) == (set(), set())

    model_1.hostname = "my_host"
    assert model_diff(model_1, model_2) == (set(), {'hostname'})

    model_2.hostname = "my_host_2"
    assert model_diff(model_1, model_2) == ({'hostname'}, set())


class TestTelemetry(TestCase):
    def setUp(self):
        self.mock_coe_client = Mock(spec=COEClient)
        self.mock_report_channel = Mock(spec=Queue)
        self.mock_status_channel = Mock(spec=Queue)
        self.uuid = NuvlaID('nuvlabox/uuid')
        self.excluded_monitors = []
        self.test_telemetry = Telemetry(self.mock_coe_client,
                                        self.mock_report_channel,
                                        self.mock_status_channel,
                                        self.uuid,
                                        self.excluded_monitors)

    @patch('nuvlaedge.agent.workers.telemetry.get_monitor')
    def test_initialize_monitors(self, mock_get_monitors):
        mock_get_monitors.return_value = Mock()
        self.test_telemetry._initialize_monitors()
        monitor_count = len(self.test_telemetry.monitor_list)

        self.test_telemetry.monitor_list = {}
        self.test_telemetry.excluded_monitors = ['power', 'container_stats']
        self.test_telemetry._initialize_monitors()
        self.assertEqual(monitor_count - 2, len(self.test_telemetry.monitor_list))

    @patch('nuvlaedge.agent.workers.telemetry.TelemetryPayloadAttributes.update')
    def test_collect_monitor_metrics(self, mock_update):
        mock_monitor = Mock()
        mock_monitor.name = 'mock_monitor'

        # Test not updated
        with patch('nuvlaedge.agent.workers.telemetry.logging.Logger.info') as mock_info:
            self.test_telemetry.monitor_list = {'mock_monitor': mock_monitor}
            mock_monitor.updated = False
            self.test_telemetry._collect_monitor_metrics()
            mock_monitor.populate_nb_report.assert_not_called()
            mock_update.assert_called_once_with({})
            mock_info.assert_called_once_with(f'Data not updated yet in monitor {mock_monitor.name}')

        # Normal execution
        mock_update.reset_mock()
        mock_monitor.reset_mock()
        mock_monitor.updated = True
        mock_monitor.populate_nb_report.return_value = None

        self.test_telemetry.monitor_list = {'mock_monitor': mock_monitor}

        self.test_telemetry._collect_monitor_metrics()
        mock_monitor.populate_nb_report.assert_called_once_with({})
        mock_update.assert_called_once_with({})

        # Test exception
        mock_update.reset_mock()
        mock_monitor.reset_mock()
        mock_monitor.updated = True
        mock_monitor.populate_nb_report.side_effect = Exception('mock_exception')
        with patch('nuvlaedge.agent.workers.telemetry.logging.Logger.exception') as mock_exception:
            self.test_telemetry._collect_monitor_metrics()
            mock_monitor.populate_nb_report.assert_called_once_with({})
            mock_update.assert_called_once_with({})
            mock_exception.assert_called_once()

    @patch('nuvlaedge.agent.workers.telemetry.is_thread_creation_needed')
    @patch('nuvlaedge.agent.workers.telemetry.get_monitor')
    @patch('nuvlaedge.agent.workers.telemetry.json')
    def test_check_monitors_health(self, mock_json, mock_get_monitor, mock_is_thread_creation_needed):
        mock_monitor = Mock()
        mock_monitor.name = 'mock_monitor'
        mock_monitor.is_thread = False

        # Test not threaded
        self.test_telemetry.monitor_list = {'mock_monitor': mock_monitor}
        self.test_telemetry._check_monitors_health()
        mock_monitor.run_update_data.assert_called_once()

        # Test no creation needed
        mock_monitor.is_thread = True
        mock_is_thread_creation_needed.return_value = False
        self.test_telemetry._check_monitors_health()
        mock_get_monitor.assert_not_called()

        # Test threaded and creation needed
        mock_is_thread_creation_needed.return_value = True
        mock_get_monitor.return_value = mock_monitor
        self.test_telemetry._check_monitors_health()
        mock_get_monitor.assert_called_once_with('mock_monitor')
        mock_monitor.assert_called_once_with('mock_monitor', self.test_telemetry, True)

    def test_sync_status_to_telemetry(self):
        test_data: NuvlaEdgeData = NuvlaEdgeData()
        test_data.operating_system = "Test_OS"

        self.test_telemetry.edge_status.nuvlaedge_info = test_data
        self.test_telemetry._sync_status_to_telemetry()
        self.assertEqual(self.test_telemetry._local_telemetry.operating_system, test_data.operating_system)

    @patch('nuvlaedge.agent.common.status_handler.NuvlaEdgeStatusHandler.running')
    @patch('nuvlaedge.agent.workers.telemetry.Telemetry._sync_status_to_telemetry')
    @patch('nuvlaedge.agent.workers.telemetry.Telemetry._check_monitors_health')
    @patch('nuvlaedge.agent.workers.telemetry.Telemetry._collect_monitor_metrics')
    def test_run(self, mock_metrics, mock_health, mock_sync_status, mock_status_handler):

        self.mock_report_channel.put.return_value = None
        self.test_telemetry.run()
        mock_metrics.assert_called_once()
        mock_health.assert_called_once()
        mock_sync_status.assert_called_once()
        mock_status_handler.assert_called_once()
        self.assertIsNotNone(self.test_telemetry._local_telemetry.current_time)
        self.mock_report_channel.put.assert_called_once_with(self.test_telemetry._local_telemetry, block=False)

        with patch('nuvlaedge.agent.workers.telemetry.logging.Logger.warning') as mock_warning:
            self.mock_report_channel.put.side_effect = Full()
            self.test_telemetry.run()
            mock_warning.assert_called_once_with("Telemetry Queue is full, agent not consuming data...")