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
import secrets

import pytest
from eth_account import Account
from web3 import Web3

from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.blockchain.eth.token import StakeList
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import StakeHolderConfiguration, UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD,
    TEMPORARY_DOMAIN,
)
from tests.constants import (
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI
)
from tests.utils.ursula import select_test_port


@pytest.fixture(scope='module')
def mock_funded_account_password_keystore(tmp_path_factory, testerchain):
    """Generate a random keypair & password and create a local keystore"""
    keystore = tmp_path_factory.mktemp('keystore', numbered=True)
    password = secrets.token_urlsafe(12)
    account = Account.create()
    path = keystore / f'{account.address}'
    json.dump(account.encrypt(password), open(path, 'x+t'))

    testerchain.wait_for_receipt(
        testerchain.client.w3.eth.sendTransaction({
            'to': account.address,
            'from': testerchain.etherbase_account,
            'value': Web3.toWei('1', 'ether')}))

    return account, password, keystore


def test_ursula_and_local_keystore_signer_integration(click_runner,
                                                      tmp_path,
                                                      manual_staker,
                                                      stake_value,
                                                      token_economics,
                                                      mocker,
                                                      mock_funded_account_password_keystore,
                                                      testerchain):
    config_root_path = tmp_path
    ursula_config_path = config_root_path / UrsulaConfiguration.generate_filename()
    stakeholder_config_path = config_root_path / StakeHolderConfiguration.generate_filename()
    worker_account, password, mock_keystore_path = mock_funded_account_password_keystore

    #
    # Stakeholder Steps
    #

    init_args = ('stake', 'init-stakeholder',
                 '--config-root', config_root_path,
                 '--provider', TEST_PROVIDER_URI,
                 '--network', TEMPORARY_DOMAIN)
    click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)

    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_config_path,
                  '--staking-address', manual_staker,
                  '--value', stake_value.to_tokens(),
                  '--lock-periods', token_economics.minimum_locked_periods,
                  '--force')
    # TODO: Is This test is writing to the default system directory and ignoring updates to the passed filepath?
    user_input = f'0\n{password}\nY\n'
    click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)

    init_args = ('stake', 'bond-worker',
                 '--config-file', stakeholder_config_path,
                 '--staking-address', manual_staker,
                 '--worker-address', worker_account.address,
                 '--force')
    user_input = password
    click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)

    #
    # Worker Steps
    #

    # Good signer...
    mock_signer_uri = f'keystore:{mock_keystore_path}'
    pre_config_signer = KeystoreSigner.from_signer_uri(uri=mock_signer_uri, testnet=True)
    assert worker_account.address in pre_config_signer.accounts

    deploy_port = select_test_port()

    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--worker-address', worker_account.address,
                 '--config-root', config_root_path,
                 '--provider', TEST_PROVIDER_URI,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', deploy_port,

                 # The bit we are testing for here
                 '--signer', mock_signer_uri)

    cli_env = {
        NUCYPHER_ENVVAR_KEYSTORE_PASSWORD:    password,
        NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD: password,
    }
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=cli_env)
    assert result.exit_code == 0, result.stdout

    # Inspect the configuration file for the signer URI
    with open(ursula_config_path, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['signer_uri'] == mock_signer_uri,\
            "Keystore URI was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(ursula_config_path)
    assert ursula_config.signer_uri == mock_signer_uri

    # Mock decryption of web3 client keystore
    mocker.patch.object(Account, 'decrypt', return_value=worker_account.privateKey)
    ursula_config.keystore.unlock(password=password)

    # Produce an Ursula with a Keystore signer correctly derived from the signer URI, and don't do anything else!
    mocker.patch.object(StakeList, 'refresh', autospec=True)
    ursula = ursula_config.produce()
    ursula.signer.unlock_account(account=worker_account.address, password=password)

    try:
        # Verify the keystore path is still preserved
        assert isinstance(ursula.signer, KeystoreSigner)
        assert isinstance(ursula.signer.path, str), "Use str"
        assert ursula.signer.path == str(mock_keystore_path)

        # Show that we can produce the exact same signer as pre-config...
        assert pre_config_signer.path == ursula.signer.path

        # ...and that transactions are signed by the keystore signer
        txhash = ursula.commit_to_next_period()
        receipt = testerchain.wait_for_receipt(txhash)
        transaction_data = testerchain.client.w3.eth.getTransaction(receipt['transactionHash'])
        assert transaction_data['from'] == worker_account.address
    finally:
        ursula.stop()
