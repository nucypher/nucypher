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

import json
import os
import pytest
from eth_account import Account
from web3 import Web3

from nucypher.blockchain.eth.signers import KeystoreSigner, Signer
from nucypher.blockchain.eth.token import StakeList
from nucypher.characters.lawful import Ursula
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD, NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD
from nucypher.utilities.sandbox.constants import (
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    TEMPORARY_DOMAIN,
)

CLI_ENV = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD,
           NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}

KEYFILE_NAME_TEMPLATE = 'UTC--2020-{month}-21T03-42-07.869432648Z--{address}'
MOCK_KEYSTORE_PATH = '/home/fakeMcfakeson/.ethereum/llamanet/keystore/'
MOCK_SIGNER_URI = f'keystore://{MOCK_KEYSTORE_PATH}'
NUMBER_OF_MOCK_ACCOUNTS = 3


@pytest.fixture(scope='module')
def mock_accounts():
    accounts = dict()
    for i in range(NUMBER_OF_MOCK_ACCOUNTS):
        account = Account.create()
        filename = KEYFILE_NAME_TEMPLATE.format(month=i+1, address=account.address)
        accounts[filename] = account
    return accounts


@pytest.fixture(scope='module')
def worker_account(mock_accounts, testerchain):
    account = list(mock_accounts.values())[0]
    tx = {'to': account.address,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}
    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)
    return account


@pytest.fixture(scope='module')
def worker_address(worker_account):
    address = worker_account.address
    return address


@pytest.fixture(scope='module')
def custom_config_filepath(custom_filepath):
    filepath = os.path.join(custom_filepath, UrsulaConfiguration.generate_filename())
    return filepath


@pytest.fixture(scope='function', autouse=True)
def mock_keystore(mock_accounts, monkeypatch, mocker):

    def mock_keyfile_reader(_keystore, path):
        try:
            account = mock_accounts[path]
        except KeyError:
            pytest.fail()
        else:
            return account.address, dict(version=3, address=account.address)

    mocker.patch('os.listdir', return_value=list(mock_accounts.keys()))
    monkeypatch.setattr(KeystoreSigner, '_KeystoreSigner__read_keyfile', mock_keyfile_reader)


@pytest.fixture(scope='module', autouse=True)
def stakeholder(click_runner,
                stakeholder_configuration_file_location,
                stake_value,
                token_economics,
                agency_local_registry,
                manual_staker,
                custom_filepath,
                worker_address):

    init_args = ('stake', 'init-stakeholder',
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--network', TEMPORARY_DOMAIN,
                 '--registry-filepath', agency_local_registry.filepath)
    click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)

    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--value', stake_value.to_tokens(),
                  '--lock-periods', token_economics.minimum_locked_periods,
                  '--force')
    # TODO: Is This test is writing to the default system directory and ignoring updates to the passed filepath?
    user_input = f'0\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + f'Y\n'
    click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)

    init_args = ('stake', 'set-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 '--worker-address', worker_address,
                 '--force')
    user_input = INSECURE_DEVELOPMENT_PASSWORD
    click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)


def test_ursula_init_with_local_keystore_signer(click_runner,
                                                custom_filepath,
                                                custom_config_filepath,
                                                agency_local_registry,
                                                worker_account,
                                                mocker,
                                                testerchain):

    # Good signer...
    pre_config_signer = KeystoreSigner.from_signer_uri(uri=MOCK_SIGNER_URI)
    assert worker_account.address in pre_config_signer.accounts

    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--worker-address', worker_account.address,
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--registry-filepath', agency_local_registry.filepath,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', MOCK_URSULA_STARTING_PORT,

                 # The bit were' testing here
                 '--signer', MOCK_SIGNER_URI)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=CLI_ENV)
    assert result.exit_code == 0, result.stdout

    # Inspect the configuration file for the signer URI
    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['signer_uri'] == MOCK_SIGNER_URI,\
            "Keystore URI was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(custom_config_filepath)
    assert ursula_config.signer_uri == MOCK_SIGNER_URI

    # Mock decryption of web3 client keyring
    mocker.patch.object(Account, 'decrypt', return_value=worker_account.privateKey)
    ursula_config.attach_keyring(checksum_address=worker_account.address)
    ursula_config.keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    # Produce an ursula with a Keystore signer correctly derived from the signer URI, and dont do anything else!
    mocker.patch.object(StakeList, 'refresh', autospec=True)
    ursula = ursula_config.produce(client_password=INSECURE_DEVELOPMENT_PASSWORD, block_until_ready=False)

    # Verify the keystore path is still preserved
    assert isinstance(ursula.signer, KeystoreSigner)
    assert ursula.signer.path == MOCK_KEYSTORE_PATH

    # Show that we can produce the exact same signer as pre-config...
    assert pre_config_signer.path == ursula.signer.path

    # ...and that transactions are signed by the keytore signer
    receipt = ursula.confirm_activity()
    transaction_data = testerchain.client.w3.eth.getTransaction(receipt['transactionHash'])
    assert transaction_data['from'] == worker_account.address
