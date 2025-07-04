import json
from pathlib import Path

import pytest

from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    TEMPORARY_DOMAIN_NAME,
)
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_ETH_PROVIDER_URI,
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI,
    YES,
)

CONFIG_CLASSES = (UrsulaConfiguration, )


ENV = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}


@pytest.mark.usefixtures("mock_registry_sources")
@pytest.mark.parametrize("config_class", CONFIG_CLASSES)
def test_initialize_via_cli(
    config_class,
    temp_dir_path,
    click_runner,
):
    command = config_class.CHARACTER_CLASS.__name__.lower()

    # Use a custom local filepath for configuration
    init_args = (
        command,
        "init",
        "--domain",
        TEMPORARY_DOMAIN_NAME,
        "--eth-endpoint",
        MOCK_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--config-root",
        str(temp_dir_path.absolute()),
    )

    if config_class == UrsulaConfiguration:
        init_args += ('--rest-host', MOCK_IP_ADDRESS)

    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=FAKE_PASSWORD_CONFIRMED + YES,
                                 catch_exceptions=False,
                                 env=ENV)
    assert result.exit_code == 0, result.output

    # CLI Output
    assert (
        str(temp_dir_path) in result.output
    ), "Configuration not in system temporary directory"

    # Files and Directories
    assert temp_dir_path.is_dir(), "Configuration file does not exist"
    assert (temp_dir_path / "keystore").is_dir(), "Keystore does not exist"


@pytest.mark.parametrize("config_class", CONFIG_CLASSES)
def test_reconfigure_via_cli(
    click_runner, temp_dir_path: Path, config_class, mocker, test_registry
):
    def fake_get_latest_registry(*args, **kwargs):
        return test_registry

    mocker.patch.object(
        ContractRegistry, "from_latest_publication", fake_get_latest_registry
    )

    custom_config_filepath = temp_dir_path / config_class.generate_filename()

    view_args = (config_class.CHARACTER_CLASS.__name__.lower(), 'config',
                 '--config-file', str(custom_config_filepath.absolute()),
                 '--debug')

    result = click_runner.invoke(nucypher_cli, view_args, env=ENV)
    assert result.exit_code == 0, result.output

    # Ensure all config fields are displayed
    config = config_class.from_configuration_file(custom_config_filepath)
    analog_payload = json.loads(config.serialize())
    for field in analog_payload:
        assert field in result.output

    # Read pre-edit state
    config = config_class.from_configuration_file(custom_config_filepath)
    assert config.eth_endpoint != TEST_ETH_PROVIDER_URI
    del config

    # Write
    view_args = (
        config_class.CHARACTER_CLASS.__name__.lower(),
        "config",
        "--config-file",
        str(custom_config_filepath.absolute()),
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
    )
    result = click_runner.invoke(nucypher_cli, view_args, env=ENV)
    assert result.exit_code == 0

    # Read again
    config = config_class.from_configuration_file(custom_config_filepath)
    analog_payload = json.loads(config.serialize())
    for field in analog_payload:
        assert field in result.output
    assert str(temp_dir_path) in result.output

    # After editing the fields have been updated
    assert config.eth_endpoint == TEST_ETH_PROVIDER_URI
