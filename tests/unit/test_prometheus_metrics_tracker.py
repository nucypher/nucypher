import pytest_twisted
from twisted.internet import threads

from nucypher.blockchain.eth.trackers.prometheus import PrometheusMetricsTracker
from nucypher.utilities.prometheus.collector import MetricsCollector


@pytest_twisted.inlineCallbacks
def test_execution_of_collectors(mocker):
    collectors = []
    for i in range(4):
        collectors.append(mocker.Mock(spec=MetricsCollector))

    tracker = PrometheusMetricsTracker(collectors=collectors, interval=45)
    try:
        d = threads.deferToThread(tracker.run)
        yield d

        for collector in collectors:
            collector.collect.assert_called_once()
    finally:
        tracker.stop()


def test_handle_errors(mocker):
    tracker = PrometheusMetricsTracker(
        collectors=[mocker.Mock(spec=MetricsCollector)], interval=45
    )
    f = mocker.Mock()
    f.getTraceback.return_value = "traceback"

    tracker.handle_errors(f)
