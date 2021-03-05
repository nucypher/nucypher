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


from collections import Counter

import maya
from typing import List
from web3.main import Web3

from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NucypherTokenAgent,
    PolicyManagerAgent,
    StakingEscrowAgent
)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import prettify_eth_amount
from nucypher.acumen.nicknames import Nickname


def paint_contract_status(registry, emitter):
    blockchain = BlockchainInterfaceFactory.get_interface()

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=registry)

    contracts = f"""
| Contract Deployments |
{token_agent.contract_name} ............ {token_agent.contract_address}
{staking_agent.contract_name} ............ {staking_agent.contract_address}
{policy_agent.contract_name} ............ {policy_agent.contract_address}
{adjudicator_agent.contract_name} .............. {adjudicator_agent.contract_address}
    """

    blockchain = f"""
| '{blockchain.client.chain_name}' Blockchain Network |
Gas Price ................ {Web3.fromWei(blockchain.client.gas_price, 'gwei')} Gwei
Provider URI ............. {blockchain.provider_uri}
Registry ................. {registry.filepath}
    """

    confirmed, pending, inactive = staking_agent.partition_stakers_by_activity()

    staking = f"""
| Staking |
Current Period ........... {staking_agent.get_current_period()}
Actively Staked Tokens ... {NU.from_nunits(staking_agent.get_global_locked_tokens())}
Stakers population ....... {staking_agent.get_staker_population()}
   Confirmed ............. {len(confirmed)}
   Pending confirmation .. {len(pending)}
   Inactive .............. {len(inactive)}

    """

    sep = '-' * 45
    emitter.echo(sep)
    emitter.echo(contracts)
    emitter.echo(sep)
    emitter.echo(blockchain)
    emitter.echo(sep)
    emitter.echo(staking)
    emitter.echo(sep)


def paint_preallocation_status(emitter, preallocation_agent, token_agent) -> None:
    blockchain = token_agent.blockchain

    staking_address = preallocation_agent.principal_contract.address

    token_balance = NU.from_nunits(token_agent.get_balance(staking_address))
    eth_balance = Web3.fromWei(blockchain.client.get_balance(staking_address), 'ether')
    initial_locked_amount = NU.from_nunits(preallocation_agent.initial_locked_amount)
    current_locked_amount = NU.from_nunits(preallocation_agent.unvested_tokens)
    available_amount = NU.from_nunits(preallocation_agent.available_balance)
    end_timestamp = preallocation_agent.end_timestamp

    width = 64
    output = f"""
{" Addresses ".center(width, "-")}
Staking contract: ... {staking_address}
Beneficiary: ........ {preallocation_agent.beneficiary}

{" Locked Tokens ".center(width, "-")}
Initial locked amount: {initial_locked_amount}
Current locked amount: {current_locked_amount}
Locked until: ........ {maya.MayaDT(epoch=end_timestamp)}

{" NU and ETH Balance ".center(width, "-")}
NU balance: .......... {token_balance}
    Available: ....... {available_amount}
ETH balance: ......... {eth_balance} ETH
"""
    emitter.echo(output)


def paint_locked_tokens_status(emitter, agent, periods) -> None:

    MAX_ROWS = 30
    period_range = list(range(1, periods + 1))
    token_counter = Counter({day: agent.get_all_locked_tokens(day) for day in period_range})

    width = 60  # Adjust to desired width
    longest_key = max(len(str(key)) for key in token_counter)
    graph_width = width - longest_key - 2
    widest = token_counter.most_common(1)[0][1]
    scale = graph_width / float(widest)

    bucket_size = periods // MAX_ROWS if periods > MAX_ROWS else 1

    emitter.echo(f"\n| Locked Tokens for next {periods} periods |\n")

    buckets = [period_range[i:i + bucket_size] for i in range(0, len(period_range), bucket_size)]

    for bucket in buckets:
        bucket_start = bucket[0]
        bucket_end = bucket[-1]

        bucket_max = max([token_counter[period] for period in bucket])
        bucket_min = min([token_counter[period] for period in bucket])
        delta = bucket_max - bucket_min

        bucket_range = f"{bucket_start} - {bucket_end}"
        box_plot = f"{int(bucket_min * scale) * '■'}{int(delta * scale) * '□'}"
        emitter.echo(f"{bucket_range:>9}: {box_plot:60}"
                     f"Min: {NU.from_nunits(bucket_min)} - Max: {NU.from_nunits(bucket_max)}")


def paint_stakers(emitter, stakers: List[str], registry: BaseContractRegistry) -> None:
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    current_period = staking_agent.get_current_period()
    emitter.echo(f"\nCurrent period: {current_period}")
    emitter.echo("\n| Stakers |\n")
    emitter.echo(f"{'Checksum address':42}  Staker information")
    emitter.echo('=' * (42 + 2 + 53))

    for staker_address in stakers:
        staker = Staker(domain=TEMPORARY_DOMAIN,
                        checksum_address=staker_address,
                        registry=registry)
        nickname = Nickname.from_seed(staker_address)
        emitter.echo(f"{staker_address}  {'Nickname:':10} {nickname} {nickname.icon}")
        tab = " " * len(staker_address)

        owned_tokens = staker.owned_tokens()
        last_committed_period = staker.last_committed_period
        worker = staker.worker_address
        is_restaking = staker.is_restaking
        is_winding_down = staker.is_winding_down
        is_taking_snapshots = staker.is_taking_snapshots

        missing_commitments = current_period - last_committed_period
        owned_in_nu = round(owned_tokens, 2)
        current_locked_tokens = round(staker.locked_tokens(periods=0), 2)
        next_locked_tokens = round(staker.locked_tokens(periods=1), 2)
        reward_amount = round(NU.from_nunits(staking_agent.calculate_staking_reward(staker_address=staker_address)), 2)

        emitter.echo(f"{tab}  {'Owned:':10} {owned_in_nu}")
        emitter.echo(f"{tab}  Staked in current period: {current_locked_tokens}")
        emitter.echo(f"{tab}  Staked in next period: {next_locked_tokens}")
        emitter.echo(f"{tab}  Unlocked: {reward_amount}")

        if is_restaking:
            emitter.echo(f"{tab}  {'Re-staking:':10} Yes")
        else:
            emitter.echo(f"{tab}  {'Re-staking:':10} No")
        emitter.echo(f"{tab}  {'Winding down:':10} {'Yes' if is_winding_down else 'No'}")
        emitter.echo(f"{tab}  {'Snapshots:':10} {'Yes' if is_taking_snapshots else 'No'}")
        emitter.echo(f"{tab}  {'Activity:':10} ", nl=False)
        if missing_commitments == -1:
            emitter.echo(f"Next period committed (#{last_committed_period})", color='green')
        elif missing_commitments == 0:
            emitter.echo(f"Current period committed (#{last_committed_period}). "
                         f"Pending commitment to next period.", color='yellow')
        elif missing_commitments == current_period:
            emitter.echo(f"Never made a commitment", color='red')
        else:
            emitter.echo(f"Missing {missing_commitments} commitments "
                         f"(last time for period #{last_committed_period})", color='red')

        emitter.echo(f"{tab}  {'Worker:':10} ", nl=False)
        if worker == NULL_ADDRESS:
            emitter.echo(f"Worker not bonded", color='red')
        else:
            emitter.echo(f"{worker}")

        fees = prettify_eth_amount(staker.calculate_policy_fee())
        emitter.echo(f"{tab}  Unclaimed fees: {fees}")

        min_rate = prettify_eth_amount(staker.min_fee_rate)
        emitter.echo(f"{tab}  Min fee rate: {min_rate}")
