import time

import requests
from twisted.internet import threads

from nucypher.cli.main import nucypher_cli
from nucypher.config.node import NodeConfiguration
from nucypher.network.nodes import Learner
from nucypher.utilities.sandbox.constants import MOCK_URSULA_STARTING_PORT, select_test_port
import pytest_twisted as pt


@pt.inlineCallbacks
def test_run_moe(click_runner, federated_ursulas):
    test_ws_port = select_test_port()

    args = ('moe',
            '--ws-port', test_ws_port,
            '--http-port', MOCK_URSULA_STARTING_PORT,
            '--dry-run')

    result = yield threads.deferToThread(click_runner.invoke,
                                         nucypher_cli, args,
                                         catch_exceptions=False)

    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert result.exit_code == 0
    assert f"Running Moe on 127.0.0.1:{MOCK_URSULA_STARTING_PORT}"
    assert f"WebSocketService starting on {test_ws_port}"

    reserved_ports = (NodeConfiguration.DEFAULT_REST_PORT, NodeConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert MOCK_URSULA_STARTING_PORT not in reserved_ports
