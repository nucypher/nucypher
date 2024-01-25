import json
from pathlib import Path

from nucypher.blockchain.eth.accounts import LocalAccount
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN_NAME,
)
from tests.constants import (
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI,
    TEST_POLYGON_PROVIDER_URI,
)
from tests.utils.ursula import select_test_port


def test_ursula_and_wallet_integration(
    click_runner,
    tmp_path,
    bond_operators,
    testerchain,
):
    config_root_path = tmp_path
    ursula_config_path = config_root_path / UrsulaConfiguration.generate_filename()

    mock_wallet_path = config_root_path / "mock_wallet.json"
    mock_wallet_path.unlink(missing_ok=True)

    wallet_password = 'thisisjustsilly2'
    keystore_password = 'wellthis2isjustsilly'

    wallet = testerchain.accounts.ursula_wallet(0)
    wallet.to_keystore(mock_wallet_path.absolute(), password=wallet_password)

    # the actual filesystem write is mocked in tests, but we still need to create the file
    mock_wallet_path.touch(exist_ok=True)

    deploy_port = select_test_port()

    init_args = (
        "ursula",
        "init",
        "--domain",
        TEMPORARY_DOMAIN_NAME,
        "--config-root",
        str(config_root_path.absolute()),
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_POLYGON_PROVIDER_URI,
        "--host",
        MOCK_IP_ADDRESS,
        "--port",
        deploy_port,
        # The bit we are testing for here
        "--wallet-filepath",
        mock_wallet_path,
        '--force'
    )

    cli_env = {
        NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: keystore_password,
        NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD: wallet_password,
    }
    result = click_runner.invoke(
        nucypher_cli, init_args, catch_exceptions=False, env=cli_env
    )
    assert result.exit_code == 0, result.stdout

    # Inspect the configuration file for the wallet filepath
    with open(ursula_config_path, "r") as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert (
            config_data["wallet_filepath"] == str(mock_wallet_path.absolute())
        ), "Wallet filepath was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(ursula_config_path)
    assert ursula_config.wallet_filepath == mock_wallet_path

    # Produce an Ursula with a Keystore signer correctly derived from the signer URI, and don't do anything else!
    ursula_config.unlock_wallet(password=wallet_password)
    ursula_config.keystore.unlock(password=keystore_password)
    ursula = ursula_config.produce()

    try:
        # Verify the keystore path is still preserved
        assert isinstance(ursula.wallet, LocalAccount)
        assert isinstance(ursula_config.wallet_filepath, Path), "Use pathlib.Path"
        assert ursula_config.wallet_filepath.absolute() == mock_wallet_path.absolute()

        # Show that we can produce the exact same signer as pre-config...
        assert wallet.address == ursula.wallet.address
    finally:
        ursula.stop()
