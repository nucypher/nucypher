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
from distutils.util import strtobool

import click
import os
import shutil
from constant_sorrow.constants import NO_CONTROL_PROTOCOL
from nacl.exceptions import CryptoError

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry, LocalContractRegistry
from nucypher.cli.actions.auth import unlock_nucypher_keyring, get_nucypher_password
from nucypher.cli.actions.network import load_seednodes
from nucypher.cli.literature import (
    FEDERATED_WARNING,
    PRODUCTION_REGISTRY_ADVISORY,
    LOCAL_REGISTRY_ADVISORY,
    CONNECTING_TO_BLOCKCHAIN
)
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


def make_cli_character(character_config,
                       emitter,
                       unlock_keyring: bool = True,
                       teacher_uri: str = None,
                       min_stake: int = 0,
                       load_preferred_teachers: bool = True,
                       **config_args):

    #
    # Pre-Init
    #

    # Handle Keyring

    if unlock_keyring:
        unlock_nucypher_keyring(emitter,
                                character_configuration=character_config,
                                password=get_nucypher_password(confirm=False))

    # Handle Teachers
    teacher_nodes = list()
    if load_preferred_teachers:
        teacher_nodes = load_seednodes(emitter,
                                       teacher_uris=[teacher_uri] if teacher_uri else None,
                                       min_stake=min_stake,
                                       federated_only=character_config.federated_only,
                                       network_domains=character_config.domains,
                                       network_middleware=character_config.network_middleware,
                                       registry=character_config.registry)

    #
    # Character Init
    #

    # Produce Character
    try:
        CHARACTER = character_config(known_nodes=teacher_nodes,
                                     network_middleware=character_config.network_middleware,
                                     **config_args)
    except (CryptoError, ValueError):
        raise character_config.keyring.AuthenticationFailed(f"Failed to unlock nucypher keyring. "
                                                            "Are you sure you provided the correct password?")

    #
    # Post-Init
    #

    if CHARACTER.controller is not NO_CONTROL_PROTOCOL:
        CHARACTER.controller.emitter = emitter  # TODO: set it on object creation? Or not set at all?

    # Federated
    if character_config.federated_only:
        emitter.message(FEDERATED_WARNING, color='yellow')

    return CHARACTER


def establish_deployer_registry(emitter,
                                registry_infile: str = None,
                                registry_outfile: str = None,
                                use_existing_registry: bool = False,
                                download_registry: bool = False,
                                dev: bool = False
                                ) -> BaseContractRegistry:

    if download_registry:
        registry = InMemoryContractRegistry.from_latest_publication()
        emitter.message(PRODUCTION_REGISTRY_ADVISORY.format(source=registry.source))
        return registry

    # Establish a contract registry from disk if specified
    filepath = registry_infile
    default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, BaseContractRegistry.REGISTRY_NAME)
    if registry_outfile:
        registry_infile = registry_infile or default_registry_filepath
        if use_existing_registry:
            try:
                _result = shutil.copyfile(registry_infile, registry_outfile)
            except shutil.SameFileError:
                raise click.BadArgumentUsage(f"--registry-infile and --registry-outfile must not be the same path '{registry_infile}'.")
        filepath = registry_outfile

    if dev:
        # TODO: Need a way to detect a geth --dev registry filepath here. (then deprecate the --dev flag)
        filepath = os.path.join(DEFAULT_CONFIG_ROOT, BaseContractRegistry.DEVELOPMENT_REGISTRY_NAME)

    registry_filepath = filepath or default_registry_filepath

    # All Done.
    registry = LocalContractRegistry(filepath=registry_filepath)
    emitter.message(LOCAL_REGISTRY_ADVISORY.format(registry_filepath=registry_filepath))

    return registry


def get_registry(network: str, registry_filepath: str = None) -> BaseContractRegistry:
    if registry_filepath:
        registry = LocalContractRegistry(filepath=registry_filepath)
    else:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)
    return registry


def connect_to_blockchain(provider_uri, emitter, debug: bool = False, light: bool = False) -> BlockchainInterface:
    try:
        # Note: Conditional for test compatibility.
        if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
            BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri,
                                                            light=light,
                                                            sync=False,
                                                            emitter=emitter)
        blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
        emitter.echo(message=CONNECTING_TO_BLOCKCHAIN)
        blockchain.connect()
        return blockchain
    except Exception as e:
        if debug:
            raise
        emitter.echo(str(e), bold=True, color='red')
        raise click.Abort


def get_env_bool(var_name: str, default: bool) -> bool:
    if var_name in os.environ:
        # TODO: which is better: to fail on an incorrect envvar, or to use the default?
        # Currently doing the former.
        return strtobool(os.environ[var_name])
    else:
        return default