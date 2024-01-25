import json
import secrets

import pytest

from nucypher.blockchain.eth.accounts import LocalAccount
from nucypher.cli.commands.ursula import UrsulaConfigOptions
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN_NAME,
)
from tests.constants import MOCK_IP_ADDRESS
from tests.utils.blockchain import TestAccount
from tests.utils.ursula import select_test_port


@pytest.fixture(scope='module')
def mock_account_password_keystore(tmp_path_factory):
    """Generate a random keypair & password and create a local keystore"""
    keystore = tmp_path_factory.mktemp('keystore', numbered=True)
    password = secrets.token_urlsafe(12)
    account = TestAccount.random()
    path = keystore / f'{account.address}'
    json.dump(account.encrypt(password), open(path, 'x+t'))
    return account, password, keystore


@pytest.mark.usefixtures("mock_registry_sources",)
def test_ursula_init_with_local_keystore_wallet(
    click_runner, temp_dir_path, mocker, testerchain, mock_account_password_keystore
):
    custom_filepath = temp_dir_path
    custom_config_filepath = temp_dir_path / UrsulaConfiguration.generate_filename()
    worker_account, password, mock_keystore_filepath = mock_account_password_keystore

    mocker.patch.object(UrsulaConfigOptions, '_check_for_existing_config', autospec=True)

    # Good wallet...
    random_wallet = TestAccount.random()
    path = custom_filepath / 'test.json'

    wallet_filepath = random_wallet.to_keystore(
        path=path,
        password=password
    )

    # the actual filesystem write is mocked in tests, but we still need to create the file
    # in order to pass the `--wallet-filepath` option since it is checked for existence
    path.touch(exist_ok=True)

    deploy_port = select_test_port()

    init_args = (
        "ursula",
        "init",
        "--domain",
        TEMPORARY_DOMAIN_NAME,
        "--eth-endpoint",
        testerchain.endpoint,
        "--polygon-endpoint",
        testerchain.endpoint,
        "--host",
        MOCK_IP_ADDRESS,
        "--port",
        deploy_port,
        "--config-root",
        str(custom_filepath.absolute()),
        # The bit we are testing here
        "--wallet-filepath",
        wallet_filepath,
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
        assert config_data['wallet_filepath'] == str(wallet_filepath.absolute()),  \
            "Wallet filepath was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(custom_config_filepath, config_root=custom_filepath)
    assert ursula_config.wallet_filepath == wallet_filepath

    # Mock decryption of web3 client keystore
    ursula_config.keystore.unlock(password=password)
    ursula_config.unlock_wallet(password=password)

    # Produce an ursula with a Keystore signer correctly derived from the signer URI, and don't do anything else!
    ursula = ursula_config.produce()

    # Verify the keystore path is still preserved
    assert isinstance(ursula.wallet, LocalAccount)
    path.unlink()
