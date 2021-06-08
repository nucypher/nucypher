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
from unittest import mock

import os
import pytest

from nucypher.characters.control.emitters import JSONRPCStdoutEmitter
from nucypher.characters.lawful import Ursula
from nucypher.cli import utils
from nucypher.cli.literature import SUCCESSFUL_DESTRUCTION, COLLECT_NUCYPHER_PASSWORD
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower
from nucypher.utilities.logging import GlobalLoggerSettings, Logger
from nucypher.policy.identity import Card
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


def test_initialize_bob_with_custom_configuration_root(custom_filepath, click_runner):
    # Use a custom local filepath for configuration
    init_args = ('bob', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath)
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0, result.exception

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output, "Configuration not in system temporary directory"
    assert "nucypher bob run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keystore')), 'KEYSTORE does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert COLLECT_NUCYPHER_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_bob_control_starts_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    init_args = ('bob', 'run', '--dry-run', '--lonely', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.exception
    assert "Bob Verifying Key" in result.output
    assert "Bob Encrypting Key" in result.output


def test_bob_make_card(click_runner, custom_filepath, mocker):
    mock_save_card = mocker.patch.object(Card, 'save')
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    command = ('bob', 'make-card', '--nickname', 'anders', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, command, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Saved new character card " in result.output
    mock_save_card.assert_called_once()


def test_bob_view_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    view_args = ('bob', 'config', '--config-file', custom_config_filepath)
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


@pytest.mark.skip("Needs mock middleware handling")  # TODO
def test_bob_retrieves_twice_via_cli(click_runner,
                                     capsule_side_channel,
                                     enacted_federated_policy,
                                     federated_ursulas,
                                     custom_filepath_2,
                                     federated_alice,
                                     federated_bob,
                                     mocker):

    teacher = list(federated_ursulas)[0]

    first_message = capsule_side_channel.reset(plaintext_passthrough=True)
    three_message_kits = [capsule_side_channel(), capsule_side_channel(), capsule_side_channel()]

    bob_config_root = custom_filepath_2
    bob_configuration_file_location = os.path.join(bob_config_root, BobConfiguration.generate_filename())
    label = enacted_federated_policy.label

    # I already have a Bob.

    # Need to init so that the config file is made, even though we won't use this Bob.
    bob_init_args = ('bob', 'init',
                     '--network', TEMPORARY_DOMAIN,
                     '--config-root', bob_config_root,
                     '--federated-only')

    envvars = {'NUCYPHER_KEYSTORE_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}

    log.info("Init'ing a normal Bob; we'll substitute the Policy Bob in shortly.")
    bob_init_response = click_runner.invoke(nucypher_cli, bob_init_args, catch_exceptions=False, env=envvars)

    message_kit_bytes = bytes(three_message_kits[0])
    message_kit_b64_bytes = b64encode(message_kit_bytes)
    UmbralMessageKit.from_bytes(message_kit_bytes)

    retrieve_args = ('bob', 'retrieve',
                     '--mock-networking',
                     '--json-ipc',
                     '--teacher', teacher.seed_node_metadata(as_teacher_uri=True),
                     '--config-file', bob_configuration_file_location,
                     '--message-kit', message_kit_b64_bytes,
                     '--label', label,
                     '--policy-encrypting-key', bytes(federated_alice.get_policy_encrypting_key_from_label(label)).hex(),
                     '--alice-verifying-key', bytes(federated_alice.public_keys(SigningPower)).hex()
                     )

    def substitute_bob(*args, **kwargs):
        log.info("Substituting the Policy's Bob in CLI runtime.")
        this_fuckin_guy = federated_bob
        somebody_else = Ursula.from_teacher_uri(teacher_uri=kwargs['teacher_uri'],
                                                min_stake=0,
                                                federated_only=True,
                                                network_middleware=this_fuckin_guy.network_middleware)
        this_fuckin_guy.remember_node(somebody_else)
        this_fuckin_guy.controller.emitter = JSONRPCStdoutEmitter()
        return this_fuckin_guy

    mocker.patch.object(utils, 'make_cli_character', return_value=substitute_bob)

    # Once...
    with GlobalLoggerSettings.pause_all_logging_while():
        retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)

    log.info(f"First retrieval response: {retrieve_response.output}")
    assert retrieve_response.exit_code == 0

    retrieve_response = json.loads(retrieve_response.output)
    for cleartext in retrieve_response['result']['cleartexts']:
        assert cleartext.encode() == capsule_side_channel.plaintexts[1]

    # and again!
    with GlobalLoggerSettings.pause_all_logging_while():
        retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)

    log.info(f"Second retrieval response: {retrieve_response.output}")
    assert retrieve_response.exit_code == 0

    retrieve_response = json.loads(retrieve_response.output)
    for cleartext in retrieve_response['result']['cleartexts']:
        assert cleartext.encode() == capsule_side_channel.plaintexts[1]


# NOTE: Should be the last test in this module since it deletes the configuration file
def test_bob_destroy(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    destroy_args = ('bob', 'destroy', '--config-file', custom_config_filepath, '--force')
    result = click_runner.invoke(nucypher_cli, destroy_args, catch_exceptions=False)
    assert result.exit_code == 0, result.exception
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not os.path.exists(custom_config_filepath), "Bob config file was deleted"
