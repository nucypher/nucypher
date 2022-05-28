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
from pathlib import Path
from typing import Optional, Type

import click
from tabulate import tabulate
from web3.main import Web3

from nucypher.blockchain.eth.agents import ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, BaseContractRegistry
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.blockchain.eth.token import NU
from nucypher.cli.actions.configure import get_config_filepaths
from nucypher.cli.literature import (
    GENERIC_SELECT_ACCOUNT,
    NO_CONFIGURATIONS_ON_DISK,
    NO_ETH_ACCOUNTS,
    SELECT_NETWORK,
    SELECTED_ACCOUNT,
    IGNORE_OLD_CONFIGURATION,
    DEFAULT_TO_LONE_CONFIG_FILE
)
from nucypher.cli.painting.policies import paint_cards
from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_OPERATOR_ADDRESS, DEFAULT_CONFIG_ROOT
from nucypher.control.emitters import StdoutEmitter
from nucypher.policy.identity import Card


def select_client_account(emitter,
                          eth_provider_uri: str = None,
                          signer: Signer = None,
                          signer_uri: str = None,
                          prompt: str = None,
                          default: int = 0,
                          registry: BaseContractRegistry = None,
                          show_eth_balance: bool = False,
                          show_nu_balance: bool = False,
                          show_staking: bool = False,
                          network: str = None,
                          poa: bool = None
                          ) -> str:
    """
    Interactively select an ethereum wallet account from a table of nucypher account metadata.

    Note: Showing ETH and/or NU balances, causes an eager blockchain connection.
    """

    if signer and signer_uri:
        raise ValueError('Pass either signer or signer_uri but not both.')

    if not any((eth_provider_uri, signer_uri, signer)):
        raise ValueError("At least a provider URI, signer URI or signer must be provided to select an account")

    if eth_provider_uri:
        # Connect to the blockchain in order to select an account
        if not BlockchainInterfaceFactory.is_interface_initialized(eth_provider_uri=eth_provider_uri):
            BlockchainInterfaceFactory.initialize_interface(eth_provider_uri=eth_provider_uri, poa=poa, emitter=emitter)
        if not signer_uri:
            signer_uri = eth_provider_uri

    blockchain = BlockchainInterfaceFactory.get_interface(eth_provider_uri=eth_provider_uri)

    if signer_uri and not signer:
        testnet = network != NetworksInventory.MAINNET
        signer = Signer.from_signer_uri(signer_uri, testnet=testnet)

    # Display accounts info
    if show_nu_balance or show_staking:  # Lazy registry fetching
        if not registry:
            if not network:
                raise ValueError("Pass network name or registry; Got neither.")
            registry = InMemoryContractRegistry.from_latest_publication(network=network)

    enumerated_accounts = dict(enumerate(signer.accounts))
    if len(enumerated_accounts) < 1:
        emitter.echo(NO_ETH_ACCOUNTS, color='red', bold=True)
        raise click.Abort()
    elif len(enumerated_accounts) == 1:
        # There are no choices if there is only one available address.
        return enumerated_accounts[0]

    # Display account info
    headers = ['Account']
    if show_staking:
        headers.append('Staking')
    if show_eth_balance:
        headers.append('ETH')
    if show_nu_balance:
        headers.append('NU')

    rows = list()
    for index, account in enumerated_accounts.items():
        row = [account]
        if show_staking:
            staker = Staker(domain=network, checksum_address=account, registry=registry)
            staker.refresh_stakes()
            is_staking = 'Yes' if bool(staker.stakes) else 'No'
            row.append(is_staking)
        if show_eth_balance:
            ether_balance = Web3.fromWei(blockchain.client.get_balance(account), 'ether')
            row.append(f'{ether_balance} ETH')
        if show_nu_balance:
            token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
            token_balance = NU.from_units(token_agent.get_balance(account, registry))
            row.append(token_balance)
        rows.append(row)
    emitter.echo(tabulate(rows, headers=headers, showindex='always'))

    # Prompt the user for selection, and return
    prompt = prompt or GENERIC_SELECT_ACCOUNT
    account_range = click.IntRange(min=0, max=len(enumerated_accounts)-1)
    choice = click.prompt(prompt, type=account_range, default=default)
    chosen_account = enumerated_accounts[choice]

    emitter.echo(SELECTED_ACCOUNT.format(choice=choice, chosen_account=chosen_account), color='blue')
    return chosen_account


def select_network(emitter: StdoutEmitter, network_type: str, message: Optional[str] = None) -> str:
    """Interactively select a network from nucypher networks inventory list"""
    emitter.message(message=message or str(), color="yellow")
    if network_type == NetworksInventory.ETH:
        network_list = NetworksInventory.ETH_NETWORKS
    elif network_type == NetworksInventory.POLYGON:
        network_list = NetworksInventory.POLY_NETWORKS
    else:
        raise(ValueError("Network type must be either 'eth' or 'polygon'"))
    rows = [[n] for n in network_list]
    emitter.echo(tabulate(rows, showindex="always"))
    choice = click.prompt(
        SELECT_NETWORK,
        default=0,
        type=click.IntRange(0, len(rows) - 1),
    )
    network = network_list[choice]
    return network


def select_config_file(emitter: StdoutEmitter,
                       config_class: Type[CharacterConfiguration],
                       config_root: Optional[Path] = None,
                       checksum_address: str = None,
                       ) -> Path:
    """
    Selects a nucypher character configuration file from the disk automatically or interactively.

    Behaviour
    ~~~~~~~~~

    - If checksum address is supplied by parameter or operator address env var - confirm there is a corresponding
      file on the disk or raise ValueError.

    - If there is only one configuration file for the character, automatically return its filepath.

    - If there are multiple character configurations on the disk in the same configuration root,
      use interactive selection.

    - Aborts if there are no configurations associated with the supplied character configuration class.

    """

    config_root = config_root or DEFAULT_CONFIG_ROOT
    config_files = get_config_filepaths(config_class=config_class, config_root=config_root)
    if not config_files:
        emitter.message(NO_CONFIGURATIONS_ON_DISK.format(name=config_class.NAME.capitalize(),
                                                         command=config_class.NAME), color='red')
        raise click.Abort()

    checksum_address = checksum_address or os.environ.get(NUCYPHER_ENVVAR_OPERATOR_ADDRESS, None)  # TODO: Deprecate operator_address in favor of checksum_address

    parsed_config_files = list()
    parsed_addresses_and_filenames = list()
    # parse configuration files for checksum address values
    for fp in config_files:
        try:
            config_checksum_address = config_class.checksum_address_from_filepath(fp)
            if checksum_address and config_checksum_address == checksum_address:
                # matching configuration file found, no need to continue - return filepath
                return fp

            parsed_config_files.append(fp)
            parsed_addresses_and_filenames.append([config_checksum_address, Path(fp).name])  # store checksum & filename
        except config_class.OldVersion:
            # no use causing entire usage to crash if file can't be used anyway - inform the user; they can
            # decide for themself
            emitter.echo(IGNORE_OLD_CONFIGURATION.format(config_file=fp), color='yellow')

    if checksum_address:
        # shouldn't get here if checksum address was specified and corresponding file found
        raise ValueError(f"'{checksum_address}' is not a known {config_class.NAME} configuration account.")

    if not parsed_config_files:
        # No available configuration files
        emitter.message(NO_CONFIGURATIONS_ON_DISK.format(name=config_class.NAME.capitalize(),
                                                         command=config_class.NAME),
                        color='red')
        raise click.Abort()
    elif len(parsed_config_files) > 1:
        #
        # Interactive
        #
        emitter.echo(f"\nConfiguration Directory: {config_root}\n")

        parsed_addresses_and_filenames = tuple(parsed_addresses_and_filenames)  # must be tuple-of-iterables for tabulation

        # Display account info
        headers = ['Account', 'Configuration File']
        emitter.echo(tabulate(parsed_addresses_and_filenames, headers=headers, showindex='always'))

        # Prompt the user for selection, and return
        prompt = f"Select {config_class.NAME} configuration"
        account_range = click.IntRange(min=0, max=len(parsed_config_files) - 1)
        choice = click.prompt(prompt, type=account_range, default=0)
        config_file = parsed_config_files[choice]
        emitter.echo(f"Selected {choice}: {config_file}", color='blue')
    else:
        # Default: Only one config file, use it.
        config_file = parsed_config_files[0]
        emitter.echo(DEFAULT_TO_LONE_CONFIG_FILE.format(config_class=config_class.NAME.capitalize(),
                                                        config_file=config_file))

    return config_file


def select_card(emitter, card_identifier: str) -> Card:
    if not card_identifier:
        cards = []
        for filename in Card.CARD_DIR.iterdir():
            filepath = Card.CARD_DIR / filename
            card = Card.load(filepath=filepath)
            cards.append(card)
        paint_cards(emitter=emitter, cards=cards, as_table=True)
        selection = click.prompt('Select card', type=click.IntRange(0, len(cards)))
        card = cards[selection]
    else:
        card = Card.load(identifier=card_identifier)
    return card
