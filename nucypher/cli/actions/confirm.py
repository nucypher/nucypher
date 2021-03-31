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


import click
from constant_sorrow.constants import UNKNOWN_DEVELOPMENT_CHAIN_ID

from maya import MayaDT
from tabulate import tabulate
from typing import Type, Union, Dict
from web3.main import Web3

from nucypher.blockchain.economics import BaseEconomics
from nucypher.blockchain.eth.deployers import BaseContractDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, VersionedContract, BlockchainInterface
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import calculate_period_duration
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.literature import (
    ABORT_DEPLOYMENT,
    CHARACTER_DESTRUCTION,
    CONFIRM_ENABLE_RESTAKING,
    CONFIRM_ENABLE_WINDING_DOWN,
    CONFIRM_LARGE_STAKE_DURATION,
    CONFIRM_LARGE_STAKE_VALUE,
    CONFIRM_STAGED_STAKE,
    RESTAKING_AGREEMENT,
    WINDING_DOWN_AGREEMENT,
    SNAPSHOTS_DISABLING_AGREEMENT,
    CONFIRM_DISABLE_SNAPSHOTS
)
from nucypher.cli.literature import CONFIRM_VERSIONED_UPGRADE
from nucypher.config.base import CharacterConfiguration


def confirm_deployment(emitter: StdoutEmitter, deployer_interface: BlockchainDeployerInterface) -> bool:
    """
    Interactively confirm deployment by asking the user to type the ALL CAPS name of
    the network they are deploying to or 'DEPLOY' if the network if not a known public chain.

    Aborts if the confirmation word is incorrect.
    """
    if deployer_interface.client.chain_name == UNKNOWN_DEVELOPMENT_CHAIN_ID or deployer_interface.client.is_local:
        expected_chain_name = 'DEPLOY'
    else:
        expected_chain_name = deployer_interface.client.chain_name
    if click.prompt(f"Type '{expected_chain_name.upper()}' to continue") != expected_chain_name.upper():
        emitter.echo(ABORT_DEPLOYMENT, color='red', bold=True)
        raise click.Abort(ABORT_DEPLOYMENT)
    return True


def confirm_enable_restaking(emitter: StdoutEmitter, staking_address: str) -> bool:
    """Interactively confirm enabling of the restaking with user agreements."""
    emitter.message(RESTAKING_AGREEMENT.format(staking_address=staking_address))
    click.confirm(CONFIRM_ENABLE_RESTAKING.format(staking_address=staking_address), abort=True)
    return True


def confirm_enable_winding_down(emitter: StdoutEmitter, staking_address: str) -> bool:
    """Interactively confirm enabling of winding down with user agreements."""
    emitter.message(WINDING_DOWN_AGREEMENT)
    click.confirm(CONFIRM_ENABLE_WINDING_DOWN.format(staking_address=staking_address), abort=True)
    return True


def confirm_disable_snapshots(emitter: StdoutEmitter, staking_address: str) -> bool:
    """Interactively confirm disabling of taking snapshots with user agreements."""
    emitter.message(SNAPSHOTS_DISABLING_AGREEMENT)
    click.confirm(CONFIRM_DISABLE_SNAPSHOTS.format(staking_address=staking_address), abort=True)
    return True


def confirm_staged_stake(staker_address: str, value: NU, lock_periods: int) -> bool:
    """Interactively confirm a new stake reviewing all staged stake details."""
    click.confirm(CONFIRM_STAGED_STAKE.format(nunits=str(value.to_nunits()),
                                              tokens=value,
                                              staker_address=staker_address,
                                              lock_periods=lock_periods), abort=True)
    return True


def confirm_large_and_or_long_stake(value: NU = None, lock_periods: int = None, economics: BaseEconomics = None) -> bool:
    """Interactively confirm a large stake and/or a long stake duration."""
    if economics and value and (value > (NU.from_nunits(economics.minimum_allowed_locked) * 10)):  # > 10x min stake
        click.confirm(CONFIRM_LARGE_STAKE_VALUE.format(value=value), abort=True)
    if economics and lock_periods and (lock_periods > economics.maximum_rewarded_periods):  # > 1 year
        lock_days = (lock_periods * economics.hours_per_period) // 24
        click.confirm(CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods, lock_days=lock_days),
                      abort=True)
    return True


def confirm_destroy_configuration(config: CharacterConfiguration) -> bool:
    """Interactively confirm destruction of nucypher configuration files"""
    # TODO: This is a workaround for ursula - needs follow up
    try:
        database = config.db_filepath
    except AttributeError:
        database = "No database found"
    confirmation = CHARACTER_DESTRUCTION.format(name=config.NAME,
                                                root=config.config_root,
                                                keystore=config.keyring_root,
                                                nodestore=config.node_storage.source,
                                                config=config.filepath,
                                                database=database)
    click.confirm(confirmation, abort=True)
    return True


def verify_upgrade_details(blockchain: Union[BlockchainDeployerInterface, BlockchainInterface],
                           registry: LocalContractRegistry,
                           deployer: Type[BaseContractDeployer],
                           ) -> None:
    """
    Compares the versions of two 'implementation' contracts using a local and source registry.
    """

    old_contract: VersionedContract = blockchain.get_contract_by_name(
        registry=registry,
        contract_name=deployer.contract_name,
        proxy_name=deployer.agency._proxy_name,
        use_proxy_address=False
    )

    new_contract = blockchain.find_raw_contract_data(contract_name=deployer.contract_name)
    new_version = new_contract[0]  # Handle index error?

    click.confirm(CONFIRM_VERSIONED_UPGRADE.format(contract_name=deployer.contract_name,
                                                   old_version=old_contract.version,
                                                   new_version=new_version), abort=True)


def confirm_staged_grant(emitter, grant_request: Dict, federated: bool, seconds_per_period=None) -> None:

    pretty_request = grant_request.copy()  # WARNING: Do not mutate

    if federated:  # Boring
        table = [[field.capitalize(), value] for field, value in pretty_request.items()]
        emitter.echo(tabulate(table, tablefmt="simple"))
        return

    period_rate = Web3.fromWei(pretty_request['n'] * pretty_request['rate'], 'gwei')
    pretty_request['rate'] = f"{pretty_request['rate']} wei/period * {pretty_request['n']} nodes"

    expiration = pretty_request['expiration']
    periods = calculate_period_duration(future_time=MayaDT.from_datetime(expiration),
                                        seconds_per_period=seconds_per_period)
    periods += 1  # current period is always included
    pretty_request['expiration'] = f"{pretty_request['expiration']} ({periods} periods)"

    # M of N
    pretty_request['Threshold Shares'] = f"{pretty_request['m']} of {pretty_request['n']}"
    del pretty_request['m']
    del pretty_request['n']

    def prettify_field(field):
        field_words = [word.capitalize() for word in field.split('_')]
        field = ' '.join(field_words)
        return field

    table = [[prettify_field(field), value] for field, value in pretty_request.items()]
    table.append(['Period Rate', f'{period_rate} gwei'])
    table.append(['Policy Value', f'{period_rate * periods} gwei'])

    emitter.echo("\nSuccessfully staged grant, Please review the details:\n", color='green')
    emitter.echo(tabulate(table, tablefmt="simple"))
    click.confirm('\nGrant access and sign transaction?', abort=True)
