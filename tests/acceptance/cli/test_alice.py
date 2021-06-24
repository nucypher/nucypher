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

import os
from unittest import mock
from unittest.mock import PropertyMock

from nucypher.cli.commands.alice import AliceConfigOptions
from nucypher.cli.literature import SUCCESSFUL_DESTRUCTION, COLLECT_NUCYPHER_PASSWORD
from nucypher.cli.main import nucypher_cli
from nucypher.config.base import CharacterConfiguration
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, TEMPORARY_DOMAIN
from nucypher.config.storages import LocalFileBasedNodeStorage
from nucypher.crypto.keystore import Keystore
from nucypher.policy.identity import Card
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH
)


@mock.patch('nucypher.config.characters.AliceConfiguration.default_filepath', return_value='/non/existent/file')
def test_missing_configuration_file(default_filepath_mock, click_runner, test_registry_source_manager):
    cmd_args = ('alice', 'run', '--network', TEMPORARY_DOMAIN)
    env = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False, env=env)
    assert result.exit_code != 0
    assert default_filepath_mock.called
    assert "nucypher alice init" in result.output


def test_initialize_alice_defaults(click_runner, mocker, custom_filepath, monkeypatch, blockchain_ursulas, tmpdir):
    monkeypatch.delenv(NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, raising=False)

    # Mock out filesystem writes
    mocker.patch.object(AliceConfiguration, 'initialize', autospec=True)
    mocker.patch.object(AliceConfiguration, 'to_configuration_file', autospec=True)
    mocker.patch.object(LocalFileBasedNodeStorage, 'all', return_value=blockchain_ursulas)

    # Mock Keystore init
    keystore = Keystore.generate(keystore_dir=tmpdir, password=INSECURE_DEVELOPMENT_PASSWORD)
    mocker.patch.object(CharacterConfiguration, 'keystore', return_value=keystore, new_callable=PropertyMock)

    # Use default alice init args
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--config-root', custom_filepath,
                 '--federated-only')
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0

    # REST Host
    assert "nucypher alice run" in result.output

    # Auth
    assert COLLECT_NUCYPHER_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts_with_mocked_keystore(click_runner, mocker, monkeypatch, custom_filepath):
    monkeypatch.delenv(NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, raising=False)

    class MockKeystore:
        is_unlocked = False
        keystore_dir = custom_filepath / 'keystore'
        keystore_path = custom_filepath / 'keystore' / 'path.json'

        def derive_crypto_power(self, power_class, *args, **kwargs):
            return power_class()

        @classmethod
        def unlock(cls, password, *args, **kwargs):
            assert password == INSECURE_DEVELOPMENT_PASSWORD
            cls.is_unlocked = True

    good_enough_config = AliceConfiguration(dev_mode=True, federated_only=True, keystore=MockKeystore())
    mocker.patch.object(AliceConfigOptions, "create_config", return_value=good_enough_config)
    init_args = ('alice', 'run', '-x', '--lonely', '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.output


def test_initialize_alice_with_custom_configuration_root(custom_filepath, click_runner, monkeypatch):
    monkeypatch.delenv(NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, raising=False)

    # Use a custom local filepath for configuration
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output, "Configuration not in system temporary directory"
    assert "nucypher alice run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keystore')), 'KEYSTORE does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, AliceConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert COLLECT_NUCYPHER_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, AliceConfiguration.generate_filename())
    run_args = ('alice', 'run', '--dry-run', '--lonely', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, run_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.exception


def test_alice_make_card(click_runner, custom_filepath, mocker):
    mock_save_card = mocker.patch.object(Card, 'save')
    custom_config_filepath = os.path.join(custom_filepath, AliceConfiguration.generate_filename())
    command = ('alice', 'make-card', '--nickname', 'flora', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, command, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0
    mock_save_card.assert_called_once()
    assert "Saved new character card " in result.output


def test_alice_cannot_init_with_dev_flag(click_runner):
    init_args = ('alice', 'init', '--network', TEMPORARY_DOMAIN, '--federated-only', '--dev')
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Cannot create a persistent development character' in result.output, \
           'Missing or invalid error message was produced.'


def test_alice_derive_policy_pubkey(click_runner):
    label = 'random_label'
    derive_key_args = ('alice', 'derive-policy-pubkey', '--label', label, '--dev')
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "policy_encrypting_key" in result.output
    assert "label" in result.output
    assert label in result.output


def test_alice_public_keys(click_runner):
    derive_key_args = ('alice', 'public-keys', '--dev')
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "alice_verifying_key" in result.output


def test_alice_view_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, AliceConfiguration.generate_filename())
    view_args = ('alice', 'config', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, view_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0
    assert "checksum_address" in result.output
    assert "domain" in result.output
    assert TEMPORARY_DOMAIN in result.output
    assert str(custom_filepath) in result.output


def test_alice_destroy(click_runner, custom_filepath):
    """Should be the last test since it deletes the configuration file"""
    custom_config_filepath = custom_filepath / AliceConfiguration.generate_filename()
    destroy_args = ('alice', 'destroy', '--config-file', custom_config_filepath, '--force')
    result = click_runner.invoke(nucypher_cli, destroy_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not custom_config_filepath.exists(), "Alice config file was deleted"
