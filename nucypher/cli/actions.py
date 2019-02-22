import shutil
import sys
from typing import List

import click
from nacl.exceptions import CryptoError
from twisted.logger import Logger

import nucypher
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.characters.lawful import Ursula
from nucypher.config.constants import DEFAULT_CONFIG_ROOT

DESTRUCTION = '''
*Permanently and irreversibly delete all* nucypher files including
    - Private and Public Keys
    - Known Nodes
    - TLS certificates
    - Node Configurations
    - Log Files

Delete {}?'''


LOG = Logger('cli.actions')


def handle_control_output(response: dict = None,
                          message: str = None,
                          json: bool = False,
                          quiet: bool = False,
                          color: str = 'white',
                          bold: bool = False,
                          ) -> None:

    try:
        if not quiet and not json:
            if response:
                for k, v in response.items():
                    click.secho(message=f'{k} ...... {v}', fg=color, bold=bold)
            elif message:
                if json:
                    sys.stdout({'result': message, 'version': nucypher.__version__})
                    click.secho(message=message, fg=color, bold=bold)
                else:
                    click.secho(message=message, fg=color, bold=bold)
            else:
                raise ValueError('Either "response" or "message" is required, but got neither.')
        elif json:
            sys.stdout(response)
    except Exception:
        LOG.debug("Error while formatting nucypher console output")
        raise


def load_seednodes(min_stake: int, federated_only: bool, teacher_uris: list = None) -> List[Ursula]:
    teacher_nodes = list()
    if teacher_uris is None:
        # Default teacher nodes can be placed here
        return teacher_nodes
    for uri in teacher_uris:
        teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                               min_stake=min_stake,
                                               federated_only=federated_only)
        teacher_nodes.append(teacher_node)
    return teacher_nodes


def destroy_system_configuration(config_class,
                                 config_file=None,
                                 network=None,
                                 config_root=None,
                                 force=False,
                                 log=LOG):

    config_root = config_root or DEFAULT_CONFIG_ROOT

    try:
        character_config = config_class.from_configuration_file(filepath=config_file, domains={network})

    except FileNotFoundError:
        config_file_location = config_file or config_class.DEFAULT_CONFIG_FILE_LOCATION

        if not force:
            message = "No configuration file found at {}; \n" \
                      "Destroy top-level configuration directory: {}?".format(config_file_location, config_root)
            click.confirm(message, abort=True)  # ABORT

        shutil.rmtree(config_root, ignore_errors=False)

    else:
        if not force:
            click.confirm(DESTRUCTION.format(character_config.config_root), abort=True)

        try:
            character_config.destroy(force=force)
        except FileNotFoundError:
            message = 'Failed: No nucypher files found at {}'.format(character_config.config_root)
            click.secho(message, fg='red')
            log.debug(message)
            raise click.Abort()
        else:
            message = "Deleted configuration files at {}".format(character_config.config_root)
            click.secho(message, fg='green')
            log.debug(message)

    return config_root


def unlock_keyring(configuration, password):
    try:
        click.secho("Decrypting keyring...", fg='blue')
        configuration.keyring.unlock(password=password)
    except CryptoError:
        raise configuration.keyring.AuthenticationFailed


def connect_to_blockchain(configuration, recompile_contracts: bool = False):
    try:
        configuration.connect_to_blockchain(recompile_contracts=recompile_contracts)
        configuration.connect_to_contracts()
    except EthereumContractRegistry.NoRegistry:
        message = "Cannot configure blockchain character: No contract registry found; " \
                  "Did you mean to pass --federated-only?"
        raise EthereumContractRegistry.NoRegistry(message)


def forget(configuration):
    """Forget all known nodes via storages"""
    click.confirm("Permanently delete all known node data?", abort=True)
    configuration.forget_nodes()
    message = "Removed all stored node node metadata and certificates"
    click.secho(message=message, fg='red')
