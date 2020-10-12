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
from typing import List

import tabulate
from web3.main import Web3

from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME, NULL_ADDRESS
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import datetime_at_period, prettify_eth_amount
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.literature import POST_STAKING_ADVICE
from nucypher.cli.painting.transactions import paint_receipt_summary

STAKE_TABLE_COLUMNS = ('Idx', 'Value', 'Remaining', 'Enactment', 'Termination', 'Status')
STAKER_TABLE_COLUMNS = ('Status', 'Restaking', 'Winding Down', 'Snapshots', 'Unclaimed Fees', 'Min fee rate')


def paint_all_stakes(emitter: StdoutEmitter,
                     stakeholder: 'StakeHolder',
                     paint_unlocked: bool = False) -> None:

    stakers = stakeholder.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")

    total_stakers = 0
    for staker in stakers:
        if not staker.stakes:
            # This staker has no active stakes.
            # TODO: Something with non-staking accounts?
            continue

        paint_stakes(emitter=emitter, staker=staker, paint_unlocked=paint_unlocked, stakeholder=stakeholder)
        total_stakers += 1

    if not total_stakers:
        emitter.echo("No Stakes found", color='red')


def paint_stakes(emitter: StdoutEmitter,
                 staker: 'Staker',
                 stakes: List[Stake] = None,
                 paint_unlocked: bool = False,
                 stakeholder=None) -> None:

    stakes = stakes or staker.sorted_stakes()

    fees = staker.policy_agent.get_fee_amount(staker.checksum_address)
    pretty_fees = prettify_eth_amount(fees)
    last_committed = staker.staking_agent.get_last_committed_period(staker.checksum_address)
    missing = staker.missing_commitments
    min_fee_rate = prettify_eth_amount(staker.min_fee_rate)

    if missing == -1:
        missing_info = "Never Made a Commitment (New Stake)"
    else:
        missing_info = f'Missing {missing} commitments{"s" if missing > 1 else ""}' if missing else f'Committed #{last_committed}'

    staker_data = [missing_info,
                   f'{"Yes" if staker.is_restaking else "No"} '
                   f'({"Locked" if staker.restaking_lock_enabled else "Unlocked"})',
                   "Yes" if bool(staker.is_winding_down) else "No",
                   "Yes" if bool(staker.is_taking_snapshots) else "No",
                   pretty_fees,
                   min_fee_rate]

    line_width = 54
    if staker.registry.source:  # TODO: #1580 - Registry source might be Falsy in tests.
        network_snippet = f"\nNetwork {staker.registry.source.network.capitalize()} "
        snippet_with_line = network_snippet + '═'*(line_width-len(network_snippet)+1)
        emitter.echo(snippet_with_line, bold=True)
    emitter.echo(f"Staker {staker.checksum_address} ════", bold=True, color='red' if missing else 'green')
    worker = staker.worker_address if staker.worker_address != NULL_ADDRESS else 'not bonded'
    emitter.echo(f"Worker {worker} ════", color='red' if staker.worker_address == NULL_ADDRESS else None)
    if stakeholder and stakeholder.worker_data:
        worker_data = stakeholder.worker_data.get(staker.checksum_address)
        if worker_data:
            emitter.echo(f"\t public address: {worker_data['publicaddress']}")
            if worker_data.get('nucypher version'):
                emitter.echo(f"\t NuCypher Version: {worker_data['nucypher version']}")
            if worker_data.get('blockchain_provider'):
                emitter.echo(f"\t Blockchain Provider: {worker_data['blockchain_provider']}")
    emitter.echo(tabulate.tabulate(zip(STAKER_TABLE_COLUMNS, staker_data), floatfmt="fancy_grid"))

    rows, inactive_substakes = list(), list()
    for index, stake in enumerate(stakes):
        if stake.status().is_child(Stake.Status.INACTIVE):
            inactive_substakes.append(index)

        if stake.status().is_child(Stake.Status.UNLOCKED) and not paint_unlocked:
            # This stake is unlocked.
            continue
        rows.append(list(stake.describe().values()))

    if not rows:
        emitter.echo(f"There are no locked stakes\n")

    emitter.echo(tabulate.tabulate(rows, headers=STAKE_TABLE_COLUMNS, tablefmt="fancy_grid"))  # newline

    if not paint_unlocked and inactive_substakes:
        emitter.echo(f"Note that some sub-stakes are inactive: {inactive_substakes}\n"
                     f"Run `nucypher stake list --all` to show all sub-stakes.", color='yellow')


def prettify_stake(stake, index: int = None) -> str:
    start_datetime = stake.start_datetime.local_datetime().strftime("%b %d %H:%M %Z")
    expiration_datetime = stake.unlock_datetime.local_datetime().strftime("%b %d %H:%M %Z")
    duration = stake.duration

    pretty_periods = f'{duration} periods {"." if len(str(duration)) == 2 else ""}'

    pretty = f'| {index if index is not None else "-"} ' \
             f'| {stake.staker_address[:6]} ' \
             f'| {stake.index} ' \
             f'| {str(stake.value)} ' \
             f'| {pretty_periods} ' \
             f'| {start_datetime} - {expiration_datetime} ' \

    return pretty


def paint_staged_stake_division(emitter,
                                blockchain,
                                stakeholder,
                                original_stake,
                                target_value,
                                extension):
    new_end_period = original_stake.final_locked_period + extension
    new_duration_periods = new_end_period - original_stake.first_locked_period + 1
    staking_address = original_stake.staker_address

    division_message = f"""
Staking address: {staking_address}
~ Original Stake: {prettify_stake(stake=original_stake, index=None)}
"""

    paint_staged_stake(emitter=emitter,
                       blockchain=blockchain,
                       stakeholder=stakeholder,
                       staking_address=staking_address,
                       stake_value=target_value,
                       lock_periods=new_duration_periods,
                       start_period=original_stake.first_locked_period,
                       unlock_period=new_end_period + 1,
                       division_message=division_message)


def paint_staged_stake(emitter,
                       blockchain,
                       stakeholder,
                       staking_address,
                       stake_value,
                       lock_periods,
                       start_period,
                       unlock_period,
                       division_message: str = None):
    start_datetime = datetime_at_period(period=start_period,
                                        seconds_per_period=stakeholder.economics.seconds_per_period,
                                        start_of_period=True)

    unlock_datetime = datetime_at_period(period=unlock_period,
                                         seconds_per_period=stakeholder.economics.seconds_per_period,
                                         start_of_period=True)

    start_datetime_pretty = start_datetime.local_datetime().strftime("%b %d %H:%M %Z")
    unlock_datetime_pretty = unlock_datetime.local_datetime().strftime("%b %d %H:%M %Z")

    if division_message:
        emitter.echo(f"\n{'═' * 30} ORIGINAL STAKE {'═' * 28}", bold=True)
        emitter.echo(division_message)

    emitter.echo(f"\n{'═' * 30} STAGED STAKE {'═' * 30}", bold=True)

    emitter.echo(f"""
Staking address: {staking_address}
~ Chain      -> ID # {blockchain.client.chain_id} | {blockchain.client.chain_name}
~ Value      -> {stake_value} ({int(stake_value)} NuNits)
~ Duration   -> {lock_periods} Days ({lock_periods} Periods)
~ Enactment  -> {start_datetime_pretty} (period #{start_period})
~ Expiration -> {unlock_datetime_pretty} (period #{unlock_period})
    """)

    # TODO: periods != Days - Do we inform the user here?

    emitter.echo('═'*73, bold=True)


def paint_staking_confirmation(emitter, staker, receipt):
    emitter.echo("\nStake initialization transaction was successful.", color='green')
    emitter.echo(f'\nTransaction details:')
    paint_receipt_summary(emitter=emitter, receipt=receipt, transaction_type="deposit stake")
    emitter.echo(f'\n{STAKING_ESCROW_CONTRACT_NAME} address: {staker.staking_agent.contract_address}', color='blue')
    emitter.echo(POST_STAKING_ADVICE, color='green')


def paint_staking_accounts(emitter, wallet, registry):
    from nucypher.blockchain.eth.actors import Staker

    rows = list()
    for account in wallet.accounts:
        eth = str(Web3.fromWei(wallet.eth_balance(account), 'ether')) + " ETH"
        nu = str(NU.from_nunits(wallet.token_balance(account, registry)))

        staker = Staker(is_me=True, checksum_address=account, registry=registry)
        staker.refresh_stakes()
        is_staking = 'Yes' if bool(staker.stakes) else 'No'
        rows.append((is_staking, account, eth, nu))
    headers = ('Staking', 'Account', 'ETH', 'NU')
    emitter.echo(tabulate.tabulate(rows, showindex=True, headers=headers, tablefmt="fancy_grid"))


def paint_fee_rate_range(emitter, policy_agent):
    minimum, default, maximum = policy_agent.get_fee_rate_range()

    range_payload = f"""
Global fee Range:
    ~ Minimum ............ {prettify_eth_amount(minimum)}
    ~ Default ............ {prettify_eth_amount(default)}
    ~ Maximum ............ {prettify_eth_amount(maximum)}"""
    emitter.echo(range_payload)


def paint_min_rate(emitter, staker):
    paint_fee_rate_range(emitter, staker.policy_agent)
    minimum = staker.min_fee_rate
    raw_minimum = staker.raw_min_fee_rate

    rate_payload = f"""
Minimum acceptable fee rate (set by staker for their associated worker):
    ~ Previously set ....... {prettify_eth_amount(raw_minimum)}
    ~ Effective ............ {prettify_eth_amount(minimum)}"""
    emitter.echo(rate_payload)
