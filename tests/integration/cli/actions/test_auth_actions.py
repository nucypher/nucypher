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

import pytest
from constant_sorrow.constants import NO_PASSWORD
from mnemonic.mnemonic import Mnemonic

from nucypher.blockchain.eth.decorators import InvalidChecksumAddress
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.auth import (
    get_client_password,
    get_nucypher_password,
    get_password_from_prompt,
    unlock_nucypher_keystore
)
from nucypher.cli.literature import (
    COLLECT_ETH_PASSWORD,
    COLLECT_NUCYPHER_PASSWORD,
    DECRYPTING_CHARACTER_KEYSTORE,
    GENERIC_PASSWORD_PROMPT
)
from nucypher.config.base import CharacterConfiguration
from nucypher.crypto import passwords
from nucypher.crypto.keystore import Keystore
from nucypher.crypto.passwords import SecretBoxAuthenticationError
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.parametrize('confirm', (True, False))
def test_get_password_from_prompt_cli_action(mocker, mock_stdin, confirm, capsys):

    # Setup
    mock_stdin.password(INSECURE_DEVELOPMENT_PASSWORD, confirm=confirm)
    test_envvar = 'NUCYPHER_TEST_ENVVAR'
    another_password = 'th1s-iS-n0t-secur3'

    mocker.patch.dict(os.environ, {test_envvar: another_password})
    result = get_password_from_prompt(confirm=confirm)
    assert result == INSECURE_DEVELOPMENT_PASSWORD
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_PASSWORD_PROMPT in captured.out
    if confirm:
        assert "Repeat for confirmation:" in captured.out

    # From env var
    mocker.patch.dict(os.environ, {test_envvar: another_password})
    result = get_password_from_prompt(confirm=confirm, envvar=test_envvar)
    assert result is not NO_PASSWORD
    assert result != INSECURE_DEVELOPMENT_PASSWORD
    assert result == another_password
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert not captured.out
    assert not captured.err


def test_get_client_password_with_invalid_address(mock_stdin):
    # `mock_stdin` used to assert the user was not prompted
    bad_address = '0xdeadbeef'
    with pytest.raises(InvalidChecksumAddress):
        get_client_password(checksum_address=bad_address)


@pytest.mark.parametrize('confirm', (True, False))
def test_get_client_password(mock_stdin, mock_account, confirm, capsys):
    mock_stdin.password(INSECURE_DEVELOPMENT_PASSWORD, confirm=confirm)
    result = get_client_password(checksum_address=mock_account.address, confirm=confirm)
    assert result == INSECURE_DEVELOPMENT_PASSWORD
    assert mock_stdin.empty()
    message = COLLECT_ETH_PASSWORD.format(checksum_address=mock_account.address)
    captured = capsys.readouterr()
    assert message in captured.out
    if confirm:
        assert "Repeat for confirmation:" in captured.out


@pytest.mark.parametrize('confirm', (True, False))
def test_get_nucypher_password(mock_stdin, mock_account, confirm, capsys):
    mock_stdin.password(INSECURE_DEVELOPMENT_PASSWORD, confirm=confirm)
    result = get_nucypher_password(emitter=StdoutEmitter(), confirm=confirm)
    assert result == INSECURE_DEVELOPMENT_PASSWORD
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert COLLECT_NUCYPHER_PASSWORD in captured.out
    if confirm:
        prompt = COLLECT_NUCYPHER_PASSWORD + f" ({Keystore._MINIMUM_PASSWORD_LENGTH} character minimum)"
        assert prompt in captured.out


def test_unlock_nucypher_keystore_invalid_password(mocker, test_emitter, alice_blockchain_test_config, capsys, tmpdir):

    # Setup
    mocker.patch.object(passwords, 'secret_box_decrypt', side_effect=SecretBoxAuthenticationError)
    mocker.patch.object(CharacterConfiguration,
                        'dev_mode',
                        return_value=False,
                        new_callable=mocker.PropertyMock)
    keystore = Keystore.generate(password=INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=tmpdir)
    alice_blockchain_test_config.attach_keystore(keystore)

    # Test
    with pytest.raises(Keystore.AuthenticationFailed):
        unlock_nucypher_keystore(emitter=test_emitter,
                                 password=INSECURE_DEVELOPMENT_PASSWORD+'typo',
                                 character_configuration=alice_blockchain_test_config)

    captured = capsys.readouterr()
    assert DECRYPTING_CHARACTER_KEYSTORE.format(name=alice_blockchain_test_config.NAME.capitalize()) in captured.out


def test_unlock_nucypher_keystore_dev_mode(mocker, test_emitter, capsys, alice_blockchain_test_config, tmpdir):

    # Setup
    unlock_spy = mocker.spy(Keystore, 'unlock')
    mocker.patch.object(CharacterConfiguration,
                        'dev_mode',
                        return_value=True,
                        new_callable=mocker.PropertyMock)
    keystore = Keystore.generate(password=INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=tmpdir)
    alice_blockchain_test_config.attach_keystore(keystore)

    result = unlock_nucypher_keystore(emitter=test_emitter,
                                      password=INSECURE_DEVELOPMENT_PASSWORD,
                                      character_configuration=alice_blockchain_test_config)

    assert result
    output = capsys.readouterr().out
    message = DECRYPTING_CHARACTER_KEYSTORE.format(name=alice_blockchain_test_config.NAME.capitalize())
    assert message in output

    unlock_spy.assert_not_called()


def test_unlock_nucypher_keystore(mocker,
                                 test_emitter,
                                 capsys,
                                 alice_blockchain_test_config,
                                 patch_keystore,
                                 tmpdir):

    # Setup
    # Do not test "real" unlocking here, just the plumbing
    unlock_spy = mocker.patch.object(Keystore, 'unlock', return_value=True)
    mocker.patch.object(CharacterConfiguration,
                        'dev_mode',
                        return_value=False,
                        new_callable=mocker.PropertyMock)
    mocker.patch.object(Mnemonic, 'detect_language', return_value='english')
    keystore = Keystore.generate(password=INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=tmpdir)
    alice_blockchain_test_config.attach_keystore(keystore)

    result = unlock_nucypher_keystore(emitter=test_emitter,
                                      password=INSECURE_DEVELOPMENT_PASSWORD,
                                      character_configuration=alice_blockchain_test_config)

    assert result
    captured = capsys.readouterr()
    message = DECRYPTING_CHARACTER_KEYSTORE.format(name=alice_blockchain_test_config.NAME.capitalize())
    assert message in captured.out

    unlock_spy.assert_called_once_with(password=INSECURE_DEVELOPMENT_PASSWORD)
