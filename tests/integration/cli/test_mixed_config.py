import shutil
from pathlib import Path

import pytest

from nucypher.blockchain.eth.registry import LocalRegistrySource
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    TEMPORARY_DOMAIN,
)
from nucypher.crypto.keystore import InvalidPassword
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_ETH_PROVIDER_URI,
    MOCK_IP_ADDRESS,
    TEST_POLYGON_PROVIDER_URI,
)


@pytest.fixture(scope='function')
def custom_filepath():
    _path = MOCK_CUSTOM_INSTALLATION_PATH
    shutil.rmtree(_path, ignore_errors=True)
    assert not _path.exists()
    yield _path
    shutil.rmtree(_path, ignore_errors=True)


def test_destroy_with_no_configurations(click_runner, custom_filepath):
    """Provide useful error messages when attempting to destroy when there is nothing to destroy"""
    assert not custom_filepath.exists()
    ursula_file_location = custom_filepath / 'ursula.json'
    destruction_args = ('ursula', 'destroy', '--config-file', str(ursula_file_location.absolute()))
    result = click_runner.invoke(nucypher_cli, destruction_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert "Error: Invalid value for '--config-file':" in result.output
    assert str(ursula_file_location) in result.output
    assert not custom_filepath.exists()


def test_corrupted_configuration(
    click_runner, custom_filepath, testerchain, test_registry, mocker
):
    #
    # Setup
    #

    # Please tell me why
    if custom_filepath.exists():
        shutil.rmtree(custom_filepath, ignore_errors=True)
    assert not custom_filepath.exists()

    alice, ursula, another_ursula, staking_provider, *all_yall = testerchain.unassigned_accounts

    #
    # Chaos
    #

    init_args = (
        "ursula",
        "init",
        "--eth-endpoint",
        MOCK_ETH_PROVIDER_URI,
        "--pre-payment-provider",
        TEST_POLYGON_PROVIDER_URI,
        "--operator-address",
        another_ursula,
        "--network",
        TEMPORARY_DOMAIN,
        "--pre-payment-network",
        TEMPORARY_DOMAIN,
        "--rest-host",
        MOCK_IP_ADDRESS,
        "--config-root",
        str(custom_filepath.absolute()),
    )

    # Fails because password is too short and the command uses incomplete args (needs either -F or blockchain details)
    envvars = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: ''}

    with pytest.raises(InvalidPassword):
        result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
        assert result.exit_code != 0

    # Ensure there is no unintentional file creation (keys, config, etc.)
    top_level_config_root = [f.name for f in custom_filepath.iterdir()]
    assert 'ursula.config' not in top_level_config_root                         # no config file was created

    assert Path(custom_filepath).exists()
    keystore = custom_filepath / 'keystore'
    assert not keystore.exists()

    known_nodes = 'known_nodes'
    path = custom_filepath / known_nodes
    assert not path.exists()

    mocker.patch.object(LocalRegistrySource, "get", return_value=dict())
    mock_registry_filepath = custom_filepath / "mock_registry.json"
    mock_registry_filepath.touch()

    # Attempt installation again, with full args
    init_args = (
        "ursula",
        "init",
        "--network",
        TEMPORARY_DOMAIN,
        "--pre-payment-network",
        TEMPORARY_DOMAIN,
        "--eth-endpoint",
        MOCK_ETH_PROVIDER_URI,
        "--pre-payment-provider",
        TEST_POLYGON_PROVIDER_URI,
        "--operator-address",
        another_ursula,
        "--rest-host",
        MOCK_IP_ADDRESS,
        "--registry-filepath",
        mock_registry_filepath,
        "--config-root",
        str(custom_filepath.absolute()),
    )

    envvars = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0, result.output

    default_filename = UrsulaConfiguration.generate_filename()

    # Ensure configuration creation
    top_level_config_root = [f.name for f in custom_filepath.iterdir()]
    assert default_filename in top_level_config_root, "JSON configuration file was not created"

    expected_fields = [
        # TODO: Only using in-memory node storage for now
        # 'known_nodes',
        'keystore',
        default_filename
    ]
    for field in expected_fields:
        assert field in top_level_config_root

    # "Corrupt" the configuration by removing the contract registry
    mock_registry_filepath.unlink()

    # Attempt destruction with invalid configuration (missing registry)
    ursula_file_location = custom_filepath / default_filename
    destruction_args = ('ursula', 'destroy', '--debug', '--config-file', str(ursula_file_location.absolute()))
    result = click_runner.invoke(nucypher_cli, destruction_args, input='Y\n', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Ensure character destruction
    top_level_config_root = [f.name for f in custom_filepath.iterdir()]
    assert default_filename not in top_level_config_root  # config file was destroyed
