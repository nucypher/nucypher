import os
from pathlib import Path
from typing import Optional, Type

import click
from tabulate import tabulate
from web3.main import Web3

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.cli.actions.configure import get_config_filepaths
from nucypher.cli.actions.migrate import migrate
from nucypher.cli.literature import (
    DEFAULT_TO_LONE_CONFIG_FILE,
    GENERIC_SELECT_ACCOUNT,
    IGNORE_OLD_CONFIGURATION,
    MIGRATE_OLD_CONFIGURATION,
    NO_ACCOUNTS,
    NO_CONFIGURATIONS_ON_DISK,
    PROMPT_TO_MIGRATE,
    SELECT_DOMAIN,
    SELECTED_ACCOUNT,
)
from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import (
    DEFAULT_CONFIG_ROOT,
    NUCYPHER_ENVVAR_OPERATOR_ADDRESS,
)
from nucypher.utilities.emitters import StdoutEmitter


def select_client_account(
    emitter,
    polygon_endpoint: str = None,
    signer: Signer = None,
    signer_uri: str = None,
    prompt: str = None,
    default: int = 0,
    show_matic_balance: bool = False,
    domain: str = None,
    poa: bool = None,
) -> str:
    """
    Interactively select an ethereum wallet account from a table of account metadata.

    Note: Showing MATIC balance causes an eager blockchain connection.
    """

    if signer and signer_uri:
        raise ValueError('Pass either signer or signer_uri but not both.')

    if not any((polygon_endpoint, signer_uri, signer)):
        raise ValueError("At least a provider URI, signer URI or signer must be provided to select an account")

    if polygon_endpoint:
        # Connect to the blockchain in order to select an account
        if not BlockchainInterfaceFactory.is_interface_initialized(
            endpoint=polygon_endpoint
        ):
            BlockchainInterfaceFactory.initialize_interface(
                endpoint=polygon_endpoint, poa=poa, emitter=emitter
            )
        if not signer_uri:
            signer_uri = polygon_endpoint

    blockchain = BlockchainInterfaceFactory.get_interface(endpoint=polygon_endpoint)

    if signer_uri and not signer:
        domain = domains.get_domain(str(domain))
        signer = Signer.from_signer_uri(signer_uri, testnet=domain.is_testnet)

    enumerated_accounts = dict(enumerate(signer.accounts))
    if len(enumerated_accounts) < 1:
        emitter.echo(NO_ACCOUNTS, color="red", bold=True)
        raise click.Abort()
    elif len(enumerated_accounts) == 1:
        # There are no choices if there is only one available address.
        return enumerated_accounts[0]

    # Display account info
    headers = ['Account']
    if show_matic_balance:
        headers.append("MATIC")

    rows = list()
    for index, account in enumerated_accounts.items():
        row = [account]
        if show_matic_balance:
            matic_balance = Web3.from_wei(
                blockchain.client.get_balance(account), "ether"
            )
            row.append(f"{matic_balance} MATIC")
        rows.append(row)
    emitter.echo(tabulate(rows, headers=headers, showindex='always'))

    # Prompt the user for selection, and return
    prompt = prompt or GENERIC_SELECT_ACCOUNT
    account_range = click.IntRange(min=0, max=len(enumerated_accounts)-1)
    choice = click.prompt(prompt, type=account_range, default=default)
    chosen_account = enumerated_accounts[choice]

    emitter.echo(SELECTED_ACCOUNT.format(choice=choice, chosen_account=chosen_account), color='blue')
    return chosen_account


def select_domain(emitter: StdoutEmitter, message: Optional[str] = None) -> str:
    """Interactively select a domain from TACo domain inventory list"""
    emitter.message(message=message or str(), color="yellow")
    domain_list = list(domains.SUPPORTED_DOMAINS)
    rows = [[n] for n in domain_list]
    emitter.echo(tabulate(rows, showindex="always"))
    choice = click.prompt(
        SELECT_DOMAIN,
        default=0,
        type=click.IntRange(0, len(rows) - 1),
    )
    domain = domain_list[choice]
    return domain


def select_config_file(
    emitter: StdoutEmitter,
    config_class: Type[CharacterConfiguration],
    config_root: Optional[Path] = None,
    checksum_address: str = None,
    do_auto_migrate: bool = False,
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

    - If the configuration file is old and:
        1. `do_auto_migration` is False then prompt user
        2. `do_auto_migration` is True then try migrating the file, and retry loading

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

    i = 0
    while i < len(config_files):
        fp = config_files[i]
        try:
            config_checksum_address = config_class.address_from_filepath(fp)
            if checksum_address and config_checksum_address == checksum_address:
                # matching configuration file found, no need to continue - return filepath
                return fp

            parsed_config_files.append(fp)
            parsed_addresses_and_filenames.append([config_checksum_address, Path(fp).name])  # store checksum & filename
        except config_class.OldVersion as e:
            attempt_migration = True
            if not do_auto_migrate:
                if not click.confirm(
                    PROMPT_TO_MIGRATE.format(config_file=fp, version=e.version)
                ):
                    emitter.echo(
                        IGNORE_OLD_CONFIGURATION.format(
                            config_file=fp, version=e.version
                        ),
                        color="yellow",
                    )
                    attempt_migration = False

            if attempt_migration:
                emitter.echo(
                    MIGRATE_OLD_CONFIGURATION.format(config_file=fp, version=e.version),
                    color="yellow",
                )
                migrate(emitter=emitter, config_file=fp)
                # retry reading migrated file
                continue

        i += 1

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
