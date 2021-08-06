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
from pathlib import Path
from unittest import mock

import os
import pytest_twisted
from twisted.internet import threads
from twisted.internet.task import Clock

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.characters.chaotic import Felix
from nucypher.cli.literature import SUCCESSFUL_DESTRUCTION
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import FelixConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, TEMPORARY_DOMAIN
from tests.constants import (INSECURE_DEVELOPMENT_PASSWORD, MOCK_CUSTOM_INSTALLATION_PATH_2, TEST_PROVIDER_URI)


@mock.patch('nucypher.config.characters.FelixConfiguration.default_filepath', return_value=Path('/non/existent/file'))
def test_missing_configuration_file(default_filepath_mock, click_runner):
    cmd_args = ('felix', 'view')
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert default_filepath_mock.called
    assert "nucypher felix init" in result.output  # TODO: Move install hints to a constants


@pytest_twisted.inlineCallbacks
def test_run_felix(click_runner, testerchain, agency_local_registry):

    clock = Clock()
    Felix._CLOCK = clock
    Felix.DISTRIBUTION_INTERVAL = 5     # seconds
    Felix.DISBURSEMENT_INTERVAL = 0.01  # hours
    Felix.STAGING_DELAY = 2  # seconds

    # Main thread (Flask)
    os.environ['NUCYPHER_FELIX_DB_SECRET'] = INSECURE_DEVELOPMENT_PASSWORD

    # Test subproc (Click)
    envvars = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_FELIX_DB_SECRET': INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_WORKER_ETH_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD,
               'FLASK_DEBUG': '1'}

    # Felix creates a system configuration
    init_args = ('felix', 'init',
                 '--debug',
                 '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                 '--checksum-address', testerchain.client.accounts[0],
                 '--config-root', str(MOCK_CUSTOM_INSTALLATION_PATH_2.absolute()),
                 '--provider', TEST_PROVIDER_URI)
    _original_read_function = LocalContractRegistry.read

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    configuration_file_location = MOCK_CUSTOM_INSTALLATION_PATH_2 / FelixConfiguration.generate_filename()

    # Felix Creates a Database
    db_args = ('felix', 'createdb',
               '--debug',
               '--config-file', str(configuration_file_location.absolute()),
               '--provider', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli, db_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Felix Runs Web Services
    def run_felix():
        args = ('felix', 'run',
                '--debug',
                '--config-file', str(configuration_file_location.absolute()),
                '--provider', TEST_PROVIDER_URI,
                '--dry-run')

        run_result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, env=envvars)
        assert run_result.exit_code == 0
        return run_result

    # A (mocked) client requests Felix's services
    def request_felix_landing_page(_result):

        # Init an equal Felix to the already running one.
        felix_config = FelixConfiguration.from_configuration_file(filepath=configuration_file_location,
                                                                  registry_filepath=agency_local_registry.filepath)

        felix_config.keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
        felix = felix_config.produce()

        # Make a flask app
        web_app = felix.make_web_app()
        test_client = web_app.test_client()

        # Register a new recipient
        response = test_client.post('/register', data={'address': testerchain.client.accounts[-1]})
        assert response.status_code == 200

        return

    def time_travel(_result):
        clock.advance(amount=60)

    # Record starting ether balance
    recipient = testerchain.client.accounts[-1]
    staker_power = TransactingPower(account=recipient, signer=Web3Signer(testerchain.client))

    staker = Staker(registry=agency_local_registry,
                    domain=TEMPORARY_DOMAIN,
                    transacting_power=staker_power)
    original_eth_balance = staker.eth_balance

    # Run the callbacks
    d = threads.deferToThread(run_felix)
    d.addCallback(request_felix_landing_page)
    d.addCallback(time_travel)

    yield d

    def confirm_airdrop(_results):
        recipient = testerchain.client.accounts[-1]
        staker = Staker(registry=agency_local_registry,
                        domain=TEMPORARY_DOMAIN,
                        transacting_power=staker_power)

        assert staker.token_balance == NU(45000, 'NU')

        # TODO: Airdrop Testnet Ethers?
        new_eth_balance = original_eth_balance + testerchain.w3.fromWei(Felix.ETHER_AIRDROP_AMOUNT, 'ether')
        assert staker.eth_balance == new_eth_balance

    staged_airdrops = Felix._AIRDROP_QUEUE
    next_airdrop = staged_airdrops[0]
    next_airdrop.addCallback(confirm_airdrop)
    yield next_airdrop

    # Felix view
    view_args = ('felix', 'view',
                 '--config-file', str(configuration_file_location.absolute()),
                 '--provider', TEST_PROVIDER_URI)
    result = click_runner.invoke(nucypher_cli, view_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert "Address" in result.output
    assert "NU" in result.output
    assert "ETH" in result.output

    # Felix accounts
    accounts_args = ('felix', 'accounts',
                     '--config-file', str(configuration_file_location.absolute()),
                     '--provider', TEST_PROVIDER_URI)
    result = click_runner.invoke(nucypher_cli, accounts_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert testerchain.client.accounts[-1] in result.output

    # Felix destroy
    destroy_args = ('felix', 'destroy',
                    '--config-file', str(configuration_file_location.absolute()),
                    '--provider', TEST_PROVIDER_URI,
                    '--force')
    result = click_runner.invoke(nucypher_cli, destroy_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not configuration_file_location.exists(), "Felix configuration file was deleted"
