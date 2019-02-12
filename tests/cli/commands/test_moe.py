import pytest_twisted as pt
import requests
from twisted.internet import threads

from nucypher.cli.main import nucypher_cli
from nucypher.config.node import NodeConfiguration
from nucypher.utilities.sandbox.constants import MOCK_URSULA_STARTING_PORT, select_test_port
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services


@pt.inlineCallbacks
def test_run_moe(click_runner, federated_ursulas):

    # Establish a running Teacher Ursula

    ursula = list(federated_ursulas)[0]
    teacher_uri = ursula.seed_node_metadata(as_teacher_uri=True)

    _ursula_output = yield threads.deferToThread(start_pytest_ursula_services, ursula=ursula)

    test_ws_port = select_test_port()
    args = ('moe',
            '--ws-port', test_ws_port,
            '--network', ':fake-domain:',
            '--teacher-uri', teacher_uri,
            '--http-port', MOCK_URSULA_STARTING_PORT,
            '--dry-run')

    result = yield threads.deferToThread(click_runner.invoke,
                                         nucypher_cli, args,
                                         catch_exceptions=False)

    assert result.exit_code == 0
    assert f"Running Moe on 127.0.0.1:{MOCK_URSULA_STARTING_PORT}"
    assert f"WebSocketService starting on {test_ws_port}"

    reserved_ports = (NodeConfiguration.DEFAULT_REST_PORT, NodeConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert MOCK_URSULA_STARTING_PORT not in reserved_ports
