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

from nucypher.blockchain.eth.token import NU
from nucypher.cli.literature import (
    ABORT_DEPLOYMENT,
    CONFIRM_ENABLE_RESTAKING,
    CONFIRM_ENABLE_WINDING_DOWN,
    CONFIRM_LARGE_STAKE_DURATION,
    CONFIRM_LARGE_STAKE_VALUE,
    CONFIRM_RESTAKING_LOCK,
    CONFIRM_STAGED_STAKE,
    RESTAKING_AGREEMENT,
    RESTAKING_LOCK_AGREEMENT,
    WINDING_DOWN_AGREEMENT
)


def confirm_deployment(emitter, deployer_interface) -> bool:
    if deployer_interface.client.chain_name == UNKNOWN_DEVELOPMENT_CHAIN_ID or deployer_interface.client.is_local:
        expected_chain_name = 'DEPLOY'
    else:
        expected_chain_name = deployer_interface.client.chain_name
    if click.prompt(f"Type '{expected_chain_name.upper()}' to continue") != expected_chain_name.upper():
        emitter.echo(ABORT_DEPLOYMENT, color='red', bold=True)
        raise click.Abort()
    return True


def confirm_enable_restaking_lock(emitter, staking_address: str, release_period: int) -> bool:
    emitter.message(RESTAKING_LOCK_AGREEMENT.format(staking_address=staking_address, release_period=release_period))
    click.confirm(CONFIRM_RESTAKING_LOCK.format(staking_address=staking_address, release_period=release_period), abort=True)
    return True


def confirm_enable_restaking(emitter, staking_address: str) -> bool:
    emitter.message(RESTAKING_AGREEMENT.format(staking_address=staking_address))
    click.confirm(CONFIRM_ENABLE_RESTAKING.format(staking_address=staking_address), abort=True)
    return True


def confirm_enable_winding_down(emitter, staking_address: str) -> bool:
    emitter.message(WINDING_DOWN_AGREEMENT)
    click.confirm(CONFIRM_ENABLE_WINDING_DOWN.format(staking_address=staking_address), abort=True)
    return True


def confirm_staged_stake(staker_address: str, value: NU, lock_periods: int) -> bool:
    click.confirm(CONFIRM_STAGED_STAKE.format(nunits=str(value.to_nunits()),
                                              tokens=str(value.to_tokens()),
                                              staker_address=staker_address,
                                              lock_periods=lock_periods), abort=True)
    return True


def confirm_large_stake(value: NU = None, lock_periods: int = None) -> bool:
    if value and (value > NU.from_tokens(150000)):
        click.confirm(CONFIRM_LARGE_STAKE_VALUE.format(value=value), abort=True)
    if lock_periods and (lock_periods > 365):
        click.confirm(CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods), abort=True)
    return True
