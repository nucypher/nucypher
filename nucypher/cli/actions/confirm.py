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

from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.token import NU
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.literature import (
    ABORT_DEPLOYMENT,
    CHARACTER_DESTRUCTION,
    CONFIRM_ENABLE_RESTAKING,
    CONFIRM_ENABLE_WINDING_DOWN,
    CONFIRM_LARGE_STAKE_DURATION,
    CONFIRM_LARGE_STAKE_VALUE,
    CONFIRM_RESTAKING_LOCK,
    CONFIRM_STAGED_STAKE,
    RESTAKING_AGREEMENT,
    RESTAKING_LOCK_AGREEMENT,
    WINDING_DOWN_AGREEMENT, SNAPSHOTS_DISABLING_AGREEMENT, CONFIRM_DISABLE_SNAPSHOTS
)
from nucypher.config.node import CharacterConfiguration


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
        raise click.Abort()
    return True


def confirm_enable_restaking_lock(emitter: StdoutEmitter, staking_address: str, release_period: int) -> bool:
    """Interactively confirm enabling of the staking lock with user agreements."""
    emitter.message(RESTAKING_LOCK_AGREEMENT.format(staking_address=staking_address, release_period=release_period))
    click.confirm(CONFIRM_RESTAKING_LOCK.format(staking_address=staking_address, release_period=release_period), abort=True)
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


def confirm_large_stake(value: NU = None, lock_periods: int = None) -> bool:
    """Interactively confirm a large stake and/or a long stake duration."""
    if value and (value > NU.from_tokens(150000)):
        click.confirm(CONFIRM_LARGE_STAKE_VALUE.format(value=value), abort=True)
    if lock_periods and (lock_periods > 365):
        click.confirm(CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods), abort=True)
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
