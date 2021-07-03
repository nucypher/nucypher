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

import click
from constant_sorrow.constants import NO_PASSWORD

from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.signers.software import ClefSigner
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.literature import (
    COLLECT_ETH_PASSWORD,
    COLLECT_NUCYPHER_PASSWORD,
    DECRYPTING_CHARACTER_KEYSTORE,
    GENERIC_PASSWORD_PROMPT,
    PASSWORD_COLLECTION_NOTICE
)
from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYSTORE_PASSWORD
from nucypher.crypto.keystore import Keystore, _WORD_COUNT


def get_password_from_prompt(prompt: str = GENERIC_PASSWORD_PROMPT, envvar: str = None, confirm: bool = False) -> str:
    """Collect a password interactively, preferring an env var is one is provided and set."""
    password = NO_PASSWORD
    if envvar:
        password = os.environ.get(envvar, NO_PASSWORD)
    if password is NO_PASSWORD:  # Collect password, prefer env var
        password = click.prompt(prompt, confirmation_prompt=confirm, hide_input=True)
    return password


@validate_checksum_address
def get_client_password(checksum_address: str, envvar: str = None, confirm: bool = False) -> str:
    """Interactively collect an ethereum client password"""
    client_password = get_password_from_prompt(prompt=COLLECT_ETH_PASSWORD.format(checksum_address=checksum_address),
                                               envvar=envvar,
                                               confirm=confirm)
    return client_password


def unlock_signer_account(config: CharacterConfiguration, json_ipc: bool) -> None:

    # TODO: Remove this block after deprecating 'worker_address'
    from nucypher.config.characters import UrsulaConfiguration
    if isinstance(config, UrsulaConfiguration):
        account = config.worker_address
    else:
        account = config.checksum_address

    is_clef = ClefSigner.is_valid_clef_uri(config.signer_uri)
    eth_password_is_needed = all((not config.federated_only,
                                  not config.signer.is_device(account=account),
                                  not config.dev_mode,
                                  not is_clef))

    __password = None
    if eth_password_is_needed:
        if json_ipc and not os.environ.get(config.SIGNER_ENVVAR):
            raise ValueError(f'{config.SIGNER_ENVVAR} is required to use JSON IPC mode.')
        __password = get_client_password(checksum_address=account, envvar=config.SIGNER_ENVVAR)
    config.signer.unlock_account(account=config.checksum_address, password=__password)


def get_nucypher_password(emitter, confirm: bool = False, envvar=NUCYPHER_ENVVAR_KEYSTORE_PASSWORD) -> str:
    """Interactively collect a nucypher password"""
    prompt = COLLECT_NUCYPHER_PASSWORD
    if confirm:
        emitter.message(PASSWORD_COLLECTION_NOTICE)
        prompt += f" ({Keystore._MINIMUM_PASSWORD_LENGTH} character minimum)"
    keystore_password = get_password_from_prompt(prompt=prompt, confirm=confirm, envvar=envvar)
    return keystore_password


def unlock_nucypher_keystore(emitter: StdoutEmitter, password: str, character_configuration: CharacterConfiguration) -> bool:
    """Unlocks a nucypher keystore and attaches it to the supplied configuration if successful."""
    emitter.message(DECRYPTING_CHARACTER_KEYSTORE.format(name=character_configuration.NAME.capitalize()), color='yellow')

    # precondition
    if character_configuration.dev_mode:
        return True  # Dev accounts are always unlocked

    # unlock
    character_configuration.keystore.unlock(password=password)  # Takes ~3 seconds, ~1GB Ram
    return True


def recover_keystore(emitter) -> None:
    emitter.message('This procedure will recover your nucypher keystore from mnemonic seed words. '
                    'You will need to provide the entire mnemonic (space seperated) in the correct '
                    'order and choose a new password.', color='cyan')
    click.confirm('Do you want to continue', abort=True)
    __words = click.prompt("Enter nucypher keystore seed words")
    word_count = len(__words.split())
    if word_count != _WORD_COUNT:
        emitter.message(f'Invalid mnemonic - Number of words must be {str(_WORD_COUNT)}, but only got {word_count}')
    __password = get_nucypher_password(emitter=emitter, confirm=True)
    keystore = Keystore.restore(words=__words, password=__password)
    emitter.message(f'Recovered nucypher keystore {keystore.id} to \n {keystore.keystore_path}', color='green')
