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

from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.blockchain.eth.token import StakeList
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYRING_PASSWORD,
    NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD,
    TEMPORARY_DOMAIN
)
from tests.constants import MOCK_IP_ADDRESS, TEST_PROVIDER_URI
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT


@pytest.fixture(scope='module')
def mock_account_password_keystore(tmp_path_factory):
    """Generate a random keypair & password and create a local keystore"""
    keystore = tmp_path_factory.mktemp('keystore', numbered=True)
    password = secrets.token_urlsafe(12)
    account = Account.create()
    path = keystore / f'{account.address}'
    json.dump(account.encrypt(password), open(path, 'x+t'))
    return account, password, keystore

@pytest.mark.usefixtures('mock_contract_agency')
def test_ursula_init_with_local_keystore_signer(click_runner,
                                                tmp_path,
                                                mocker,
                                                mock_testerchain,
                                                mock_account_password_keystore,
                                                test_registry_source_manager):
    custom_filepath = tmp_path
    custom_config_filepath = tmp_path / UrsulaConfiguration.generate_filename()
    worker_account, password, mock_keystore_path = mock_account_password_keystore
    mock_signer_uri = f'keystore:{mock_keystore_path}'

    # Good signer...
    pre_config_signer = KeystoreSigner.from_signer_uri(uri=mock_signer_uri)

    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--worker-address', worker_account.address,
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', MOCK_URSULA_STARTING_PORT,

                 # The bit we are testing here
                 '--signer', mock_signer_uri)

    cli_env = {
        NUCYPHER_ENVVAR_KEYRING_PASSWORD:    password,
        NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD: password,
    }
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 catch_exceptions=False,
                                 env=cli_env)
    assert result.exit_code == 0, result.stdout

    # Inspect the configuration file for the signer URI
    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['signer_uri'] == mock_signer_uri,\
            "Keystore URI was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(custom_config_filepath)
    assert ursula_config.signer_uri == mock_signer_uri

    # Mock decryption of web3 client keyring
    mocker.patch.object(Account, 'decrypt', return_value=worker_account.privateKey)
    ursula_config.attach_keyring(checksum_address=worker_account.address)
    ursula_config.keyring.unlock(password=password)

    # Produce an ursula with a Keystore signer correctly derived from the signer URI, and dont do anything else!
    mocker.patch.object(StakeList, 'refresh', autospec=True)
    ursula = ursula_config.produce(client_password=password,
                                   block_until_ready=False)

    # Verify the keystore path is still preserved
    assert isinstance(ursula.signer, KeystoreSigner)
    assert isinstance(ursula.signer.path, str), "Use str"
    assert ursula.signer.path == str(mock_keystore_path)

    # Show that we can produce the exact same signer as pre-config...
    assert pre_config_signer.path == ursula.signer.path
    ursula.stop()
