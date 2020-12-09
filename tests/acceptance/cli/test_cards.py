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

from pathlib import Path

import os

import pytest
import tempfile
from umbral.keys import UmbralPrivateKey

from tests.constants import YES
from nucypher.cli.commands.contacts import contacts
from nucypher.cli.main import nucypher_cli
from nucypher.policy.identity import Card


@pytest.fixture(scope='module', autouse=True)
def patch_card_directory(module_mocker):
    custom_filepath = '/tmp/nucypher-test-cards-'
    tmpdir = tempfile.TemporaryDirectory(prefix=custom_filepath)
    tmpdir.cleanup()
    module_mocker.patch.object(Card, 'CARD_DIR', return_value=Path(tmpdir.name),
                               new_callable=module_mocker.PropertyMock)
    yield
    tmpdir.cleanup()


@pytest.fixture(scope='module')
def alice_verifying_key():
    return UmbralPrivateKey.gen_key().get_pubkey().hex()


@pytest.fixture(scope='module')
def bob_nickname():
    return 'edward'.capitalize()


@pytest.fixture(scope='module')
def alice_nickname():
    return 'alice'.capitalize()


@pytest.fixture(scope='module')
def bob_verifying_key():
    return UmbralPrivateKey.gen_key().get_pubkey().hex()


@pytest.fixture(scope='module')
def bob_encrypting_key():
    return UmbralPrivateKey.gen_key().get_pubkey().hex()



def test_contacts_help(click_runner):
    derive_key_args = ('contacts', '--help')
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    normalized_help_text = ' '.join(result.output.split())
    assert contacts.__doc__ in normalized_help_text


def test_list_cards_with_none_created(click_runner, certificates_tempdir):
    derive_key_args = ('contacts', 'list')
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert f'No cards found at {Card.CARD_DIR}.' in result.output


def test_create_alice_card(click_runner, alice_verifying_key, alice_nickname):
    derive_key_args = ('contacts', 'create')
    user_input = (
        'a',                  # Alice
        alice_verifying_key,  # Public key
        alice_nickname        # Nickname
    )
    user_input = '\n'.join(user_input)
    assert len(os.listdir(Card.CARD_DIR)) == 0
    result = click_runner.invoke(nucypher_cli, derive_key_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert 'Enter Verifying Key' in result.output
    assert 'Saved new card' in result.output
    assert len(os.listdir(Card.CARD_DIR)) == 1


def test_create_bob_card(click_runner, bob_nickname, bob_encrypting_key, bob_verifying_key):
    derive_key_args = ('contacts', 'create')
    user_input = (
        'b',                 # Bob
        bob_encrypting_key,  # Public key 1
        bob_verifying_key,   # Public key 2
        bob_nickname         # Nickname
    )
    user_input = '\n'.join(user_input)

    assert len(os.listdir(Card.CARD_DIR)) == 1
    result = click_runner.invoke(nucypher_cli, derive_key_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert 'Enter Verifying Key' in result.output
    assert 'Enter Encrypting Key' in result.output
    assert 'Saved new card' in result.output
    assert len(os.listdir(Card.CARD_DIR)) == 2


def test_show_unknown_card(click_runner, alice_nickname, alice_verifying_key):
    derive_key_args = ('contacts', 'show', 'idontknowwhothatis')
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert 'Unknown card nickname or ID' in result.output


def test_show_alice_card(click_runner, alice_nickname, alice_verifying_key):
    derive_key_args = ('contacts', 'show', alice_nickname)
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert alice_nickname in result.output
    assert alice_verifying_key in result.output


def test_show_bob_card(click_runner, bob_nickname, bob_encrypting_key, bob_verifying_key):
    derive_key_args = ('contacts', 'show', bob_nickname)
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert bob_nickname in result.output
    assert bob_encrypting_key in result.output
    assert bob_verifying_key in result.output


def test_list_card(click_runner, bob_nickname, bob_encrypting_key,
                   bob_verifying_key, alice_nickname, alice_verifying_key):
    derive_key_args = ('contacts', 'list')
    assert len(os.listdir(Card.CARD_DIR)) == 2
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert bob_nickname in result.output
    assert bob_encrypting_key[:Card.TRUNCATE] in result.output
    assert bob_verifying_key[:Card.TRUNCATE] in result.output
    assert alice_nickname in result.output
    assert alice_verifying_key[:Card.TRUNCATE] in result.output


def test_delete_card(click_runner, bob_nickname):
    derive_key_args = ('contacts', 'delete', '--id', bob_nickname, '--force')
    assert len(os.listdir(Card.CARD_DIR)) == 2
    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert 'Deleted card' in result.output
    assert len(os.listdir(Card.CARD_DIR)) == 1
