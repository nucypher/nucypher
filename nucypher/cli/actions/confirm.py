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


def confirm_deployment(emitter, deployer_interface) -> bool:
    if deployer_interface.client.chain_name == UNKNOWN_DEVELOPMENT_CHAIN_ID or deployer_interface.client.is_local:
        expected_chain_name = 'DEPLOY'
    else:
        expected_chain_name = deployer_interface.client.chain_name

    if click.prompt(f"Type '{expected_chain_name}' to continue") != expected_chain_name:
        emitter.echo("Aborting Deployment", color='red', bold=True)
        raise click.Abort()

    return True


def confirm_enable_restaking_lock(emitter, staking_address: str, release_period: int) -> bool:
    restaking_lock_agreement = f"""
By enabling the re-staking lock for {staking_address}, you are committing to automatically
re-stake all rewards until a future period.  You will not be able to disable re-staking until {release_period}.
    """
    emitter.message(restaking_lock_agreement)
    click.confirm(f"Confirm enable re-staking lock for staker {staking_address} until {release_period}?", abort=True)
    return True


def confirm_enable_restaking(emitter, staking_address: str) -> bool:
    restaking_agreement = f"By enabling the re-staking for {staking_address}, " \
                          f"all staking rewards will be automatically added to your existing stake."
    emitter.message(restaking_agreement)
    click.confirm(f"Confirm enable automatic re-staking for staker {staking_address}?", abort=True)
    return True


def confirm_enable_winding_down(emitter, staking_address: str) -> bool:
    winding_down_agreement = f"""
Over time, as the locked stake duration decreases
i.e. `winds down`, you will receive decreasing inflationary rewards.

Instead, by disabling `wind down` (default) the locked stake duration
can remain constant until you specify that `wind down` should begin. By
keeping the locked stake duration constant, it ensures that you will
receive maximum inflation compensation.

If `wind down` was previously disabled, you can enable it at any point
and the locked duration will decrease after each period.

For more information see https://docs.nucypher.com/en/latest/architecture/sub_stakes.html#winding-down.
"""
    emitter.message(winding_down_agreement)
    click.confirm(f"Confirm enable automatic winding down for staker {staking_address}?", abort=True)
    return True


def confirm_staged_stake(staker_address, value, lock_periods) -> None:
    click.confirm(f"""
* Ursula Node Operator Notice *
-------------------------------

By agreeing to stake {str(value)} ({str(value.to_nunits())} NuNits):

- Staked tokens will be locked for the stake duration.

- You are obligated to maintain a networked and available Ursula-Worker node
  bonded to the staker address {staker_address} for the duration
  of the stake(s) ({lock_periods} periods).

- Agree to allow NuCypher network users to carry out uninterrupted re-encryption
  work orders at-will without interference.

Failure to keep your node online, or violation of re-encryption work orders
will result in the loss of staked tokens as described in the NuCypher slashing protocol.

Keeping your Ursula node online during the staking period and successfully
producing correct re-encryption work orders will result in rewards
paid out in ethers retro-actively and on-demand.

Accept ursula node operator obligation?""", abort=True)


def issue_stake_suggestions(value: NU = None, lock_periods: int = None) -> None:
    if value and (value > NU.from_tokens(150000)):
        click.confirm(f"Wow, {value} - That's a lot of NU - Are you sure this is correct?", abort=True)
    if lock_periods and (lock_periods > 365):
        click.confirm(f"Woah, {lock_periods} is a long time - Are you sure this is correct?", abort=True)