import json
import secrets
from pathlib import Path

import pytest
from eth_account import Account

from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN,
)
from tests.constants import MOCK_IP_ADDRESS
from tests.utils.ursula import select_test_port


@pytest.fixture(scope='module')
def mock_account_password_keystore(tmp_path_factory):
    """Generate a random keypair & password and create a local keystore"""
    keystore = tmp_path_factory.mktemp('keystore', numbered=True)
    password = secrets.token_urlsafe(12)
    account = Account.create()
    path = keystore / f'{account.address}'
    json.dump(account.encrypt(password), open(path, 'x+t'))
    return account, password, keystore


@pytest.mark.usefixtures(
    "mock_registry_sources", "monkeypatch_get_staking_provider_from_operator"
)
def test_ursula_init_with_local_keystore_signer(
    click_runner, temp_dir_path, mocker, testerchain, mock_account_password_keystore
):
    custom_filepath = temp_dir_path
    custom_config_filepath = temp_dir_path / UrsulaConfiguration.generate_filename()
    worker_account, password, mock_keystore_path = mock_account_password_keystore
    mock_signer_uri = f'keystore://{mock_keystore_path}'

    # Good signer...
    pre_config_signer = KeystoreSigner.from_signer_uri(uri=mock_signer_uri, testnet=True)

    deploy_port = select_test_port()

    init_args = (
        "ursula",
        "init",
        # Layer 1
        "--network",
        TEMPORARY_DOMAIN,
        "--eth-endpoint",
        testerchain.eth_provider_uri,
        # Layer 2
        "--pre-payment-network",
        TEMPORARY_DOMAIN,
        "--pre-payment-provider",
        testerchain.eth_provider_uri,
        "--rest-host",
        MOCK_IP_ADDRESS,
        "--rest-port",
        deploy_port,
        "--operator-address",
        worker_account.address,
        "--config-root",
        str(custom_filepath.absolute()),
        # The bit we are testing here
        "--signer",
        mock_signer_uri,
    )

    cli_env = {
        NUCYPHER_ENVVAR_KEYSTORE_PASSWORD:    password,
        NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD: password,
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
    ursula_config = UrsulaConfiguration.from_configuration_file(custom_config_filepath, config_root=custom_filepath)
    assert ursula_config.signer_uri == mock_signer_uri

    # Mock decryption of web3 client keystore
    mocker.patch.object(Account, 'decrypt', return_value=worker_account.key)
    ursula_config.keystore.unlock(password=password)

    # Produce an ursula with a Keystore signer correctly derived from the signer URI, and don't do anything else!
    ursula = ursula_config.produce()
    ursula.signer.unlock_account(account=worker_account.address, password=password)

    # Verify the keystore path is still preserved
    assert isinstance(ursula.signer, KeystoreSigner)
    assert isinstance(ursula.signer.path, Path), "Use pathlib.Path"
    assert ursula.signer.path.absolute() == mock_keystore_path.absolute()

    # Show that we can produce the exact same signer as pre-config...
    assert pre_config_signer.path == ursula.signer.path
    ursula.stop()
