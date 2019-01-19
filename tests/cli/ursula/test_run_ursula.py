"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import pytest_twisted as pt
import time
from twisted.internet import threads

from nucypher.characters.base import Learner
from nucypher.cli.main import nucypher_cli
from nucypher.config.node import NodeConfiguration
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_URSULA_STARTING_PORT
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services


@pt.inlineCallbacks
def test_run_lone_federated_default_development_ursula(click_runner):
    args = ('ursula', 'run',
            '--federated-only',                         # Operating Mode
            '--rest-port', MOCK_URSULA_STARTING_PORT,   # Network Port
            '--dev',                                    # Run in development mode (ephemeral node)
            '--debug',                                  # Display log output; Do not attach console
            '--dry-run',                                # Disable twisted reactor
            '--lonely'                                  # Do not load seednodes
            )

    result = yield threads.deferToThread(click_runner.invoke,
                                         nucypher_cli, args,
                                         catch_exceptions=False,
                                         input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert result.exit_code == 0
    assert "Running Ursula on 127.0.0.1:{}".format(MOCK_URSULA_STARTING_PORT)

    reserved_ports = (NodeConfiguration.DEFAULT_REST_PORT, NodeConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert MOCK_URSULA_STARTING_PORT not in reserved_ports


@pt.inlineCallbacks
def test_federated_ursula_learns_via_cli(click_runner, federated_ursulas):

    # Establish a running Teacher Ursula

    teacher = list(federated_ursulas)[0]
    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)

    _ursula_output = yield threads.deferToThread(start_pytest_ursula_services, ursula=teacher)

    args = ('ursula', 'run',
            '--federated-only',                         # Operating Mode
            '--rest-port', MOCK_URSULA_STARTING_PORT,   # Network Port
            '--teacher-uri', teacher_uri,
            '--dev',                                    # Run in development mode (ephemeral node)
            '--debug',                                  # Display log output; Do not attach console
            '--dry-run'                                 # Disable twisted reactor
            )

    result = yield threads.deferToThread(click_runner.invoke,
                                         nucypher_cli, args,
                                         catch_exceptions=False,
                                         input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

    assert result.exit_code == 0
    assert "Running Ursula on 127.0.0.1:{}".format(MOCK_URSULA_STARTING_PORT+101)

    reserved_ports = (NodeConfiguration.DEFAULT_REST_PORT, NodeConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert MOCK_URSULA_STARTING_PORT not in reserved_ports

    # Check that CLI Ursula reports that it remembers the teacher and saves the TLS certificate
    assert teacher.checksum_public_address in result.output
    assert f"Saved TLS certificate for {teacher.nickname}" in result.output
    assert f"Remembering {teacher.nickname}" in result.output
