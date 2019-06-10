"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import time

import pytest
import pytest_twisted as pt
from twisted.internet import threads

from nucypher.characters.base import Learner
from nucypher.cli import actions
from nucypher.cli.actions import UnknownIPAddress
from nucypher.cli.main import nucypher_cli
from nucypher.config.node import CharacterConfiguration
from nucypher.utilities.sandbox.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_URSULA_STARTING_PORT,
    TEMPORARY_DOMAIN
)
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services


@pt.inlineCallbacks
def test_run_lone_federated_default_development_ursula(click_runner):
    args = ('--debug',                                  # Display log output; Do not attach console
            'ursula', 'run',                            # Stat Ursula Command
            '--federated-only',                         # Operating Mode
            '--rest-port', MOCK_URSULA_STARTING_PORT,   # Network Port
            '--dev',                                    # Run in development mode (ephemeral node)
            '--dry-run',                                # Disable twisted reactor in subprocess
            '--lonely'                                  # Do not load seednodes
            )

    result = yield threads.deferToThread(click_runner.invoke,
                                         nucypher_cli, args,
                                         catch_exceptions=False,
                                         input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert result.exit_code == 0
    assert "Running" in result.output
    assert "127.0.0.1:{}".format(MOCK_URSULA_STARTING_PORT) in result.output

    reserved_ports = (CharacterConfiguration.DEFAULT_REST_PORT, CharacterConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert MOCK_URSULA_STARTING_PORT not in reserved_ports


@pt.inlineCallbacks
def test_federated_ursula_learns_via_cli(click_runner, federated_ursulas):

    # Establish a running Teacher Ursula

    teacher = list(federated_ursulas)[0]
    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)

    # Some Ursula is running somewhere
    def run_teacher():
        start_pytest_ursula_services(ursula=teacher)
        return teacher_uri

    def run_ursula(teacher_uri):

        args = ('--debug',                                  # Display log output; Do not attach console
                'ursula', 'run',
                '--federated-only',                         # Operating Mode
                '--rest-port', MOCK_URSULA_STARTING_PORT,   # Network Port
                '--teacher-uri', teacher_uri,
                '--dev',                                    # Run in development mode (ephemeral node)
                '--dry-run'                                 # Disable twisted reactor
                )

        result = yield threads.deferToThread(click_runner.invoke,
                                             nucypher_cli, args,
                                             catch_exceptions=False,
                                             input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

        assert result.exit_code == 0
        assert "Running Ursula" in result.output
        assert "127.0.0.1:{}".format(MOCK_URSULA_STARTING_PORT+101) in result.output

        reserved_ports = (CharacterConfiguration.DEFAULT_REST_PORT, CharacterConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
        assert MOCK_URSULA_STARTING_PORT not in reserved_ports

        # Check that CLI Ursula reports that it remembers the teacher and saves the TLS certificate
        assert teacher.checksum_address in result.output
        assert f"Saved TLS certificate for {teacher.nickname}" in result.output
        assert f"Remembering {teacher.nickname}" in result.output

    # Run the Callbacks
    d = threads.deferToThread(run_teacher)
    d.addCallback(run_ursula)

    yield d


def test_ursula_cannot_init_with_dev_flag(click_runner):
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--dev')
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Cannot create a persistent development character' in result.output, 'Missing or invalid error message was produced.'


def test_ursula_rest_host_determination(click_runner):

    # Patch the get_external_ip call
    original_call = actions.get_external_ip_from_centralized_source
    try:
        actions.get_external_ip_from_centralized_source = lambda: '192.0.2.0'

        args = ('ursula', 'init',
                '--federated-only',
                '--network', TEMPORARY_DOMAIN
                )

        user_input = f'Y\n{INSECURE_DEVELOPMENT_PASSWORD}\n{INSECURE_DEVELOPMENT_PASSWORD}'

        result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False,
                                     input=user_input)

        assert result.exit_code == 0
        assert '(192.0.2.0)' in result.output

        args = ('ursula', 'init',
                '--federated-only',
                '--network', TEMPORARY_DOMAIN,
                '--force'
                )

        user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n{INSECURE_DEVELOPMENT_PASSWORD}\n'

        result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False,
                                     input=user_input)

        assert result.exit_code == 0
        assert '192.0.2.0' in result.output

        # Patch get_external_ip call to error output
        def amazing_ip_oracle():
            raise UnknownIPAddress
        actions.get_external_ip_from_centralized_source = amazing_ip_oracle

        args = ('ursula', 'init',
                '--federated-only',
                '--network', TEMPORARY_DOMAIN,
                '--force'
                )

        user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n{INSECURE_DEVELOPMENT_PASSWORD}\n'

        result = click_runner.invoke(nucypher_cli, args, catch_exceptions=True, input=user_input)
        assert result.exit_code == 1
        assert isinstance(result.exception, UnknownIPAddress)

    finally:
        # Unpatch call
        actions.get_external_ip_from_centralized_source = original_call
