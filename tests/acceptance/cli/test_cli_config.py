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
from pathlib import Path

import pytest

from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration, BobConfiguration, UrsulaConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, TEMPORARY_DOMAIN
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    YES
)

CONFIG_CLASSES = (AliceConfiguration, BobConfiguration, UrsulaConfiguration)


ENV = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}


@pytest.mark.parametrize('config_class', CONFIG_CLASSES)
def test_initialize_via_cli(config_class, custom_filepath: Path, click_runner, monkeypatch):
    command = config_class.CHARACTER_CLASS.__name__.lower()

    # Use a custom local filepath for configuration
    init_args = (command, 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', str(custom_filepath.absolute()))

    if config_class == UrsulaConfiguration:
        init_args += ('--rest-host', MOCK_IP_ADDRESS)

    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=FAKE_PASSWORD_CONFIRMED + YES,
                                 catch_exceptions=False,
                                 env=ENV)
    assert result.exit_code == 0, result.output

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output, "Configuration not in system temporary directory"

    # Files and Directories
    assert custom_filepath.is_dir(), 'Configuration file does not exist'
    assert (custom_filepath / 'keystore').is_dir(), 'Keystore does not exist'
    assert (custom_filepath / 'known_nodes').is_dir(), 'known_nodes directory does not exist'


@pytest.mark.parametrize('config_class', CONFIG_CLASSES)
def test_reconfigure_via_cli(click_runner, custom_filepath: Path, config_class, monkeypatch, test_registry):

    def fake_get_latest_registry(*args, **kwargs):
        return test_registry
    monkeypatch.setattr(InMemoryContractRegistry, 'from_latest_publication', fake_get_latest_registry)

    custom_config_filepath = custom_filepath / config_class.generate_filename()

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
    assert config.federated_only
    assert config.provider_uri != TEST_PROVIDER_URI
    del config

    # Write
    view_args = (config_class.CHARACTER_CLASS.__name__.lower(), 'config',
                 '--config-file', str(custom_config_filepath.absolute()),
                 '--decentralized',
                 '--provider', TEST_PROVIDER_URI)
    result = click_runner.invoke(nucypher_cli, view_args, env=ENV)
    assert result.exit_code == 0

    # Read again
    config = config_class.from_configuration_file(custom_config_filepath)
    analog_payload = json.loads(config.serialize())
    for field in analog_payload:
        assert field in result.output
    assert str(custom_filepath) in result.output

    # After editing the fields have been updated
    assert not config.federated_only
    assert config.provider_uri == TEST_PROVIDER_URI
