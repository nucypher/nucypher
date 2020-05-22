import os
import pytest
from constant_sorrow.constants import NO_PASSWORD
from nacl.exceptions import CryptoError

from nucypher.blockchain.eth.decorators import InvalidChecksumAddress
from nucypher.cli.actions.auth import (
    get_client_password,
    get_nucypher_password,
    get_password_from_prompt,
    unlock_nucypher_keyring
)
from nucypher.cli.literature import (
    COLLECT_ETH_PASSWORD,
    COLLECT_NUCYPHER_PASSWORD,
    DECRYPTING_CHARACTER_KEYRING,
    GENERIC_PASSWORD_PROMPT
)
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import CharacterConfiguration
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.parametrize('confirm', (True, False))
def test_get_password_from_prompt_cli_action(mock_click_prompt, mock_click_confirm, confirm):

    # Setup
    mock_click_prompt.return_value = INSECURE_DEVELOPMENT_PASSWORD
    mock_click_confirm.return_value = True

    # Test
    result = get_password_from_prompt(confirm=confirm)
    assert result
    assert result is not NO_PASSWORD
    assert result == INSECURE_DEVELOPMENT_PASSWORD

    mock_click_prompt.assert_called_once_with(GENERIC_PASSWORD_PROMPT,
                                              confirmation_prompt=confirm,
                                              hide_input=True)


@pytest.mark.parametrize('confirm', (True, False))
def test_get_password_from_prompt_cli_action(mocker, mock_click_prompt, mock_click_confirm, confirm):

    # Setup
    mock_click_prompt.return_value = INSECURE_DEVELOPMENT_PASSWORD
    mock_click_confirm.return_value = True
    test_envavr = 'NUCYPHER_TEST_ENVVAR'
    another_password = 'th1s-iS-n0t-secur3'

    mocker.patch.dict(os.environ, {test_envavr: another_password})
    result = get_password_from_prompt(confirm=confirm)
    assert result == INSECURE_DEVELOPMENT_PASSWORD
    mock_click_prompt.assert_called_once_with(GENERIC_PASSWORD_PROMPT,
                                              confirmation_prompt=confirm,
                                              hide_input=True)

    mock_click_prompt.reset()

    # From env var
    mocker.patch.dict(os.environ, {test_envavr: another_password})
    result = get_password_from_prompt(confirm=confirm, envvar=test_envavr)
    assert result is not NO_PASSWORD
    assert result != INSECURE_DEVELOPMENT_PASSWORD
    assert result == another_password
    mock_click_prompt.assert_called_once_with(GENERIC_PASSWORD_PROMPT,
                                              confirmation_prompt=confirm,
                                              hide_input=True)


def test_get_client_password_with_invalid_address(mock_click_prompt, mock_account):
    bad_address = '0xdeadbeef'
    with pytest.raises(InvalidChecksumAddress):
        get_client_password(checksum_address=bad_address)


@pytest.mark.parametrize('confirm', (True, False))
def test_get_client_password(mock_click_prompt, mock_account, confirm):
    mock_click_prompt.return_value = INSECURE_DEVELOPMENT_PASSWORD
    result = get_client_password(checksum_address=mock_account.address, confirm=confirm)
    assert result == INSECURE_DEVELOPMENT_PASSWORD
    message = COLLECT_ETH_PASSWORD.format(checksum_address=mock_account.address)
    mock_click_prompt.assert_called_once_with(message, confirmation_prompt=confirm, hide_input=True)


@pytest.mark.parametrize('confirm', (True, False))
def test_get_nucypher_password(mock_click_prompt, mock_account, confirm):
    mock_click_prompt.return_value = INSECURE_DEVELOPMENT_PASSWORD
    result = get_nucypher_password(confirm=confirm)
    assert result == INSECURE_DEVELOPMENT_PASSWORD
    prompt = COLLECT_NUCYPHER_PASSWORD
    if confirm:
        prompt += f" ({NucypherKeyring.MINIMUM_PASSWORD_LENGTH} character minimum)"
    mock_click_prompt.assert_called_once_with(prompt, confirmation_prompt=confirm, hide_input=True)


def test_unlock_nucypher_keyring_invalid_password(mocker, test_emitter, stdout_trap, alice_blockchain_test_config):

    # Setup
    keyring_attach_spy = mocker.spy(CharacterConfiguration, 'attach_keyring')
    mocker.patch.object(NucypherKeyring, 'unlock', side_effect=CryptoError)
    mocker.patch.object(CharacterConfiguration,
                        'dev_mode',
                        return_value=False,
                        new_callable=mocker.PropertyMock)

    # Test
    with pytest.raises(NucypherKeyring.AuthenticationFailed):
        unlock_nucypher_keyring(emitter=test_emitter,
                                password=INSECURE_DEVELOPMENT_PASSWORD+'typo',
                                character_configuration=alice_blockchain_test_config)
    keyring_attach_spy.assert_called_once()


def test_unlock_nucypher_keyring_dev_mode(mocker, test_emitter, stdout_trap, alice_blockchain_test_config):

    # Setup
    unlock_spy = mocker.spy(NucypherKeyring, 'unlock')
    attach_spy = mocker.spy(CharacterConfiguration, 'attach_keyring')
    mocker.patch.object(CharacterConfiguration,
                        'dev_mode',
                        return_value=True,
                        new_callable=mocker.PropertyMock)
    # Test
    result = unlock_nucypher_keyring(emitter=test_emitter,
                                     password=INSECURE_DEVELOPMENT_PASSWORD,
                                     character_configuration=alice_blockchain_test_config)

    assert result
    output = stdout_trap.getvalue()
    message = DECRYPTING_CHARACTER_KEYRING.format(name=alice_blockchain_test_config.NAME)
    assert message in output

    unlock_spy.assert_not_called()
    attach_spy.assert_not_called()


def test_unlock_nucypher_keyring(mocker,
                                 test_emitter,
                                 stdout_trap,
                                 alice_blockchain_test_config,
                                 patch_keystore,
                                 tmpdir):

    # Setup
    # Do not test "real" unlocking here, just the plumbing
    unlock_spy = mocker.patch.object(NucypherKeyring, 'unlock', reeturn_value=True)
    attach_spy = mocker.spy(CharacterConfiguration, 'attach_keyring')
    mocker.patch.object(CharacterConfiguration,
                        'dev_mode',
                        return_value=False,
                        new_callable=mocker.PropertyMock)
    # Test
    result = unlock_nucypher_keyring(emitter=test_emitter,
                                     password=INSECURE_DEVELOPMENT_PASSWORD,
                                     character_configuration=alice_blockchain_test_config)

    assert result
    output = stdout_trap.getvalue()
    message = DECRYPTING_CHARACTER_KEYRING.format(name=alice_blockchain_test_config.NAME)
    assert message in output

    unlock_spy.assert_called_once_with(password=INSECURE_DEVELOPMENT_PASSWORD)
    attach_spy.assert_called_once()
