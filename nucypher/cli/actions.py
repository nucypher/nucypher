import shutil
from typing import List

import click
from nacl.exceptions import CryptoError
from twisted.logger import Logger

from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.characters.lawful import Ursula
from nucypher.cli.config import NucypherClickConfig
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.network.middleware import RestMiddleware

DESTRUCTION = '''
*Permanently and irreversibly delete all* nucypher files including
    - Private and Public Keys
    - Known Nodes
    - TLS certificates
    - Node Configurations
    - Log Files

Delete {}?'''


LOG = Logger('cli.actions')

console_emitter = NucypherClickConfig.emit


def load_seednodes(min_stake: int,
                   federated_only: bool,
                   network_middleware: RestMiddleware = None,
                   teacher_uris: list = None
                   ) -> List[Ursula]:

    teacher_nodes = list()
    if teacher_uris is None:
        # Default teacher nodes can be placed here
        return teacher_nodes
    for uri in teacher_uris:
        teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                               min_stake=min_stake,
                                               federated_only=federated_only,
                                               network_middleware=network_middleware)
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
            console_emitter(message=message, color='red')
            log.debug(message)
            raise click.Abort()
        else:
            message = "Deleted configuration files at {}".format(character_config.config_root)
            console_emitter(message=message, color='green')
            log.debug(message)

    return config_root


def unlock_keyring(configuration, password):
    try:
        console_emitter(message="Decrypting keyring...", color='blue')
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
    """Forget all known nodes via storage"""
    click.confirm("Permanently delete all known node data?", abort=True)
    configuration.forget_nodes()
    message = "Removed all stored node node metadata and certificates"
    console_emitter(message=message, color='red')
    click.secho(message=message, fg='red')
