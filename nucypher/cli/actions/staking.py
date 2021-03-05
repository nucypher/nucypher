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

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.token import Stake
from nucypher.cli.literature import PERIOD_ADVANCED_WARNING, SUCCESSFUL_STAKE_REMOVAL, CONFIRM_REMOVE_SUBSTAKE
from nucypher.cli.painting.staking import paint_stakes
from nucypher.cli.painting.transactions import paint_receipt_summary


def remove_inactive_substake(emitter,
                             stakeholder: StakeHolder,
                             action_period: int,
                             stake: Stake,
                             chain_name: str,
                             force: bool
                             ) -> None:
    # Non-interactive: Consistency check to prevent the above agreement from going stale.
    last_second_current_period = stakeholder.staker.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo(PERIOD_ADVANCED_WARNING, color='red')
        raise click.Abort

    if not force:
        click.confirm(CONFIRM_REMOVE_SUBSTAKE.format(stake_index=stake.index), abort=True)

    # Execute
    receipt = stakeholder.staker.remove_inactive_stake(stake=stake)

    # Report
    emitter.echo(SUCCESSFUL_STAKE_REMOVAL, color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter, receipt=receipt, chain_name=chain_name)
    paint_stakes(emitter=emitter, staker=stakeholder.staker)
