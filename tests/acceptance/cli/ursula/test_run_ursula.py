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


from unittest import mock

import os
import pytest
import pytest_twisted as pt
import time
from twisted.internet import threads

from nucypher import utilities
from nucypher.blockchain.eth.actors import Worker
from nucypher.characters.base import Learner
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD, TEMPORARY_DOMAIN
from nucypher.network.nodes import Teacher
from nucypher.utilities.networking import UnknownIPAddress
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    YES_ENTER
)
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT, start_pytest_ursula_services


@mock.patch('glob.glob', return_value=list())
def test_missing_configuration_file(default_filepath_mock, click_runner):
    cmd_args = ('ursula', 'run', '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert "No Ursula configurations found.  run 'nucypher ursula init' then try again." in result.output


def test_ursula_rest_host_determination(click_runner, mocker):

    # Patch the get_external_ip call
    mocker.patch.object(utilities.networking, 'get_external_ip_from_centralized_source', return_value=MOCK_IP_ADDRESS)
    mocker.patch.object(UrsulaConfiguration, 'to_configuration_file', return_value=None)

    args = ('ursula', 'init', '--federated-only', '--network', TEMPORARY_DOMAIN)
    user_input = YES_ENTER + FAKE_PASSWORD_CONFIRMED
    result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, input=user_input)
    assert result.exit_code == 0
    assert MOCK_IP_ADDRESS in result.output

    args = ('ursula', 'init', '--federated-only', '--network', TEMPORARY_DOMAIN, '--force')
    result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0
    assert MOCK_IP_ADDRESS in result.output

    # Patch get_external_ip call to error output
    mocker.patch.object(utilities.networking, 'get_external_ip_from_centralized_source', side_effect=UnknownIPAddress)
    args = ('ursula', 'init', '--federated-only', '--network', TEMPORARY_DOMAIN, '--force')
    result = click_runner.invoke(nucypher_cli, args, catch_exceptions=True, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 1
    assert isinstance(result.exception, UnknownIPAddress)


@pt.inlineCallbacks
def test_run_lone_federated_default_development_ursula(click_runner):
    args = ('ursula', 'run',                            # Stat Ursula Command
            '--debug',                                  # Display log output; Do not attach console
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

    reserved_ports = (UrsulaConfiguration.DEFAULT_REST_PORT, UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
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

        args = ('ursula', 'run',
                '--debug',                                  # Display log output; Do not attach console
                '--federated-only',                         # Operating Mode
                '--rest-port', MOCK_URSULA_STARTING_PORT,   # Network Port
                '--teacher', teacher_uri,
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

        reserved_ports = (UrsulaConfiguration.DEFAULT_REST_PORT, UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
        assert MOCK_URSULA_STARTING_PORT not in reserved_ports

        # Check that CLI Ursula reports that it remembers the teacher and saves the TLS certificate
        assert teacher.checksum_address in result.output
        assert f"Saved TLS certificate for {teacher.nickname}" in result.output
        assert f"Remembering {teacher.nickname}" in result.output

    # Run the Callbacks
    d = threads.deferToThread(run_teacher)
    d.addCallback(run_ursula)

    yield d

@pytest.mark.skip("Let's put this on ice until we get 2099 and Treasure Island working together.")
@pt.inlineCallbacks
def test_persistent_node_storage_integration(click_runner,
                                             custom_filepath,
                                             testerchain,
                                             blockchain_ursulas,
                                             agency_local_registry):

    alice, ursula, another_ursula, felix, staker, *all_yall = testerchain.unassigned_accounts
    filename = UrsulaConfiguration.generate_filename()
    another_ursula_configuration_file_location = os.path.join(custom_filepath, filename)

    init_args = ('ursula', 'init',
                 '--provider', TEST_PROVIDER_URI,
                 '--worker-address', another_ursula,
                 '--network', TEMPORARY_DOMAIN,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--config-root', custom_filepath,
                 '--registry-filepath', agency_local_registry.filepath,
                 )

    envvars = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    teacher = blockchain_ursulas.pop()
    teacher_uri = teacher.rest_information()[0].uri

    start_pytest_ursula_services(ursula=teacher)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'

    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--interactive',
                '--config-file', another_ursula_configuration_file_location,
                '--teacher', teacher_uri)

    Worker.BONDING_TIMEOUT = 1
    with pytest.raises(Teacher.UnbondedWorker):
        # Worker init success, but not bonded.
        result = yield threads.deferToThread(click_runner.invoke,
                                             nucypher_cli, run_args,
                                             catch_exceptions=False,
                                             input=user_input,
                                             env=envvars)
    assert result.exit_code == 0

    # Run an Ursula amidst the other configuration files
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--interactive',
                '--config-file', another_ursula_configuration_file_location)

    with pytest.raises(Teacher.UnbondedWorker):
        # Worker init success, but not bonded.
        result = yield threads.deferToThread(click_runner.invoke,
                                             nucypher_cli, run_args,
                                             catch_exceptions=False,
                                             input=user_input,
                                             env=envvars)
    assert result.exit_code == 0
