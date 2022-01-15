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
from base64 import b64encode
from pathlib import Path
from unittest import mock

from nucypher.cli.commands.bob import BobCharacterOptions
from nucypher.cli.literature import SUCCESSFUL_DESTRUCTION, COLLECT_NUCYPHER_PASSWORD
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.control.emitters import JSONRPCStdoutEmitter
from nucypher.crypto.powers import SigningPower
from nucypher.policy.identity import Card
from nucypher.utilities.logging import GlobalLoggerSettings, Logger
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH
)

log = Logger()


@mock.patch('nucypher.config.characters.BobConfiguration.default_filepath', return_value='/non/existent/file')
def test_missing_configuration_file(default_filepath_mock, click_runner):
    cmd_args = ('bob', 'run')
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert default_filepath_mock.called
    assert "nucypher bob init" in result.output


def test_initialize_bob_with_custom_configuration_root(click_runner, custom_filepath: Path):
    # Use a custom local filepath for configuration
    init_args = ('bob', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', str(custom_filepath.absolute()))
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0, result.exception

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output, "Configuration not in system temporary directory"
    assert "nucypher bob run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert custom_filepath.is_dir(), 'Configuration file does not exist'
    assert (custom_filepath / 'keystore').is_dir(), 'Keystore does not exist'
    assert (custom_filepath / 'known_nodes').is_dir(), 'known_nodes directory does not exist'

    custom_config_filepath = custom_filepath / BobConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

    # Auth
    assert COLLECT_NUCYPHER_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_bob_control_starts_with_preexisting_configuration(click_runner, custom_filepath: Path):
    custom_config_filepath = custom_filepath / BobConfiguration.generate_filename()
    init_args = ('bob', 'run', '--dry-run', '--lonely', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.exception
    assert "Bob Verifying Key" in result.output
    assert "Bob Encrypting Key" in result.output


def test_bob_make_card(click_runner, custom_filepath: Path, mocker):
    mock_save_card = mocker.patch.object(Card, 'save')
    custom_config_filepath = custom_filepath / BobConfiguration.generate_filename()
    command = ('bob', 'make-card', '--nickname', 'anders', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nucypher_cli, command, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Saved new character card " in result.output
    mock_save_card.assert_called_once()


def test_bob_view_with_preexisting_configuration(click_runner, custom_filepath: Path):
    custom_config_filepath = custom_filepath / BobConfiguration.generate_filename()
    view_args = ('bob', 'config', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nucypher_cli, view_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.exception
    assert "checksum_address" in result.output
    assert "domain" in result.output
    assert TEMPORARY_DOMAIN in result.output
    assert str(custom_filepath) in result.output


def test_bob_public_keys(click_runner):
    derive_key_args = ('bob', 'public-keys', '--lonely', '--dev')
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "bob_encrypting_key" in result.output
    assert "bob_verifying_key" in result.output


def test_bob_retrieve_and_decrypt(click_runner,
                                  capsule_side_channel,
                                  enacted_federated_policy,
                                  federated_ursulas,
                                  custom_filepath_2: Path,
                                  federated_alice,
                                  federated_bob,
                                  mocker):

    teacher = list(federated_ursulas)[0]

    first_message, _ = capsule_side_channel.reset(plaintext_passthrough=True)
    message_kits_b64 = [b64encode(bytes(message_kit)).decode() for message_kit in
                            [first_message, capsule_side_channel(), capsule_side_channel(), capsule_side_channel()]
                       ]

    bob_config_root = custom_filepath_2
    bob_configuration_file_location = bob_config_root / BobConfiguration.generate_filename()

    # I already have a Bob.

    # Need to init so that the config file is made, even though we won't use this Bob.
    bob_init_args = ('bob', 'init',
                     '--network', TEMPORARY_DOMAIN,
                     '--config-root', str(bob_config_root.absolute()),
                     '--federated-only')

    envvars = {'NUCYPHER_KEYSTORE_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}

    log.info("Init'ing a normal Bob; we'll substitute the Policy Bob in shortly.")
    bob_init_response = click_runner.invoke(nucypher_cli, bob_init_args, catch_exceptions=False, env=envvars)
    assert bob_init_response.exit_code == 0, bob_init_response.output

    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)
    bob_config_file = str(bob_configuration_file_location.absolute())
    policy_encrypting_key_hex = bytes(enacted_federated_policy.public_key).hex()
    alice_verifying_key_hex = bytes(federated_alice.public_keys(SigningPower)).hex()
    encrypted_treasure_map_b64 = b64encode(bytes(enacted_federated_policy.treasure_map)).decode()

    # Retrieve without --alice_verifying_key or --alice specified - tests override of schema definition for CLI
    retrieve_args = ('bob', 'retrieve-and-decrypt',
                     '--mock-networking',
                     '--json-ipc',
                     '--teacher', teacher_uri,
                     '--config-file', bob_config_file,
                     '--message-kit', message_kits_b64[0],
                     '--treasure-map', encrypted_treasure_map_b64,
                     )
    retrieve_response = click_runner.invoke(nucypher_cli,
                                            retrieve_args,
                                            catch_exceptions=False,
                                            env=envvars)
    assert retrieve_response.exit_code != 0, "no alice_verifying_key specified"
    assert "Pass either '--alice_verifying_key' or '--alice'; got neither" in retrieve_response.output, retrieve_response.output

    # Retrieve with both --alice_verifying_key and --alice specified - should not be allowed
    retrieve_args = ('bob', 'retrieve-and-decrypt',
                     '--mock-networking',
                     '--json-ipc',
                     '--teacher', teacher_uri,
                     '--config-file', bob_config_file,
                     '--message-kit', message_kits_b64[0],
                     '--alice-verifying-key', alice_verifying_key_hex,
                     '--alice', 'rando-card-nickname',
                     '--treasure-map', encrypted_treasure_map_b64,
                     )
    retrieve_response = click_runner.invoke(nucypher_cli,
                                            retrieve_args,
                                            catch_exceptions=False,
                                            env=envvars)
    assert retrieve_response.exit_code != 0, "both alice_verifying_key and alice can't be specified"
    assert "Pass either '--alice_verifying_key' or '--alice'; got both" in retrieve_response.output, retrieve_response.output

    #
    # Perform actual retrieve and decrypts
    #
    def substitute_bob(*args, **kwargs):
        log.info("Substituting the Bob used in the CLI runtime.")
        this_fuckin_guy = federated_bob
        this_fuckin_guy.controller.emitter = JSONRPCStdoutEmitter()
        return this_fuckin_guy

    with mocker.patch.object(BobCharacterOptions, 'create_character', side_effect=substitute_bob):
        #
        # Retrieve one message kit
        #
        retrieve_args = ('bob', 'retrieve-and-decrypt',
                         '--mock-networking',
                         '--json-ipc',
                         '--teacher', teacher_uri,
                         '--config-file', bob_config_file,
                         '--message-kit', message_kits_b64[0],
                         '--alice-verifying-key', alice_verifying_key_hex,
                         '--treasure-map', encrypted_treasure_map_b64,
                         )
        with GlobalLoggerSettings.pause_all_logging_while():
            retrieve_response = click_runner.invoke(nucypher_cli,
                                                    retrieve_args,
                                                    catch_exceptions=False,
                                                    env=envvars)

        log.info(f"Retrieval response: {retrieve_response.output}")
        assert retrieve_response.exit_code == 0, retrieve_response.output

        retrieve_response = json.loads(retrieve_response.output)
        cleartexts = retrieve_response['result']['cleartexts']
        assert len(cleartexts) == 1
        assert cleartexts[0].encode() == capsule_side_channel.plaintexts[0]

        #
        # Retrieve and decrypt multiple message kits
        #
        retrieve_args = ('bob', 'retrieve-and-decrypt',
                         '--mock-networking',
                         '--json-ipc',
                         '--teacher', teacher_uri,
                         '--config-file', bob_config_file,
                         # use multiple message kits
                         '--message-kit', message_kits_b64[0],
                         '--message-kit', message_kits_b64[1],
                         '--message-kit', message_kits_b64[2],
                         '--message-kit', message_kits_b64[3],
                         '--alice-verifying-key', alice_verifying_key_hex,
                         '--treasure-map', encrypted_treasure_map_b64
                         )
        with GlobalLoggerSettings.pause_all_logging_while():
            retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)

        log.info(f"Retrieval response: {retrieve_response.output}")
        assert retrieve_response.exit_code == 0, retrieve_response.output

        retrieve_response = json.loads(retrieve_response.output)
        cleartexts = retrieve_response['result']['cleartexts']
        assert len(cleartexts) == len(message_kits_b64)
        for index, cleartext in enumerate(cleartexts):
            assert cleartext.encode() == capsule_side_channel.plaintexts[index]


# NOTE: Should be the last test in this module since it deletes the configuration file
def test_bob_destroy(click_runner, custom_filepath: Path):
    custom_config_filepath = custom_filepath / BobConfiguration.generate_filename()
    destroy_args = ('bob', 'destroy', '--config-file', str(custom_config_filepath.absolute()), '--force')
    result = click_runner.invoke(nucypher_cli, destroy_args, catch_exceptions=False)
    assert result.exit_code == 0, result.exception
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not custom_config_filepath.exists(), "Bob config file was deleted"
