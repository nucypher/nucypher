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
import maya

from nucypher.blockchain.eth.agents import ContractAgency, WorkLockAgent
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import prettify_eth_amount


def paint_worklock_claim(emitter, bidder_address: str, network: str, provider_uri: str):
    message = f"""

Successfully claimed WorkLock tokens for {bidder_address}.

You can check that the stake was created correctly by running:

  nucypher status stakers --staking-address {bidder_address} --network {network} --provider {provider_uri}

Next Steps for WorkLock Winners
===============================

Congratulations! You're officially a Staker in the NuCypher network.

See the official NuCypher documentation for a comprehensive guide on next steps!

As a first step, you need to bond a worker to your stake by running:

  nucypher stake set-worker --worker-address <WORKER ADDRESS>

"""
    emitter.echo(message, color='green')


def paint_worklock_status(emitter, registry: BaseContractRegistry):
    from maya import MayaDT

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    blockchain = worklock_agent.blockchain

    # Time
    bidding_start = MayaDT(worklock_agent.start_bidding_date)
    bidding_end = MayaDT(worklock_agent.end_bidding_date)
    cancellation_end = MayaDT(worklock_agent.end_cancellation_date)

    bidding_duration = bidding_end - bidding_start
    cancellation_duration = cancellation_end - bidding_start

    now = maya.now()
    bidding_remaining = bidding_end - now if bidding_end > now else 'Closed'
    cancellation_remaining = cancellation_end - now if cancellation_end > now else "Closed"

    cancellation_open = bidding_start <= now <= cancellation_end
    bidding_open = bidding_start <= now <= bidding_end

    # Refund
    refund_multiple = worklock_agent.boosting_refund / worklock_agent.slowing_refund

    payload = f"""
Time
══════════════════════════════════════════════════════

Contribution Period ({'Open' if bidding_open else 'Closed'})
------------------------------------------------------
Claims Available ...... {'Yes' if worklock_agent.is_claiming_available() else 'No'}
Start Date ............ {bidding_start}
End Date .............. {bidding_end}
Duration .............. {bidding_duration}
Time Remaining ........ {bidding_remaining} 

Cancellation Period ({'Open' if cancellation_open else 'Closed'})
------------------------------------------------------
End Date .............. {cancellation_end}
Duration .............. {cancellation_duration}
Time Remaining ........ {cancellation_remaining}
 
 
Economics
══════════════════════════════════════════════════════

Participation
------------------------------------------------------
Lot Size .............. {NU.from_nunits(worklock_agent.lot_value)} 
Min. Allowed Bid ...... {prettify_eth_amount(worklock_agent.minimum_allowed_bid)}
Participants .......... {worklock_agent.get_bidders_population()}
ETH Supply ............ {prettify_eth_amount(worklock_agent.get_eth_supply())}
ETH Pool .............. {prettify_eth_amount(blockchain.client.get_balance(worklock_agent.contract_address))}

Base (minimum bid)
------------------------------------------------------
Base Deposit Rate ..... {worklock_agent.get_base_deposit_rate()} NU per base ETH

Bonus (surplus over minimum bid)
------------------------------------------------------
Bonus ETH Supply ...... {prettify_eth_amount(worklock_agent.get_bonus_eth_supply())}
Bonus Lot Size ........ {NU.from_nunits(worklock_agent.get_bonus_lot_value())}
Bonus Deposit Rate .... {worklock_agent.get_bonus_deposit_rate()} NU per bonus ETH

Refunds
------------------------------------------------------
Refund Rate Multiple .. {refund_multiple:.2f}
Bonus Refund Rate ..... {worklock_agent.get_bonus_refund_rate()} units of work to unlock 1 bonus ETH
Base Refund Rate ...... {worklock_agent.get_base_refund_rate()} units of work to unlock 1 base ETH

    * NOTE: bonus ETH is refunded before base ETH
    """
    emitter.echo(payload)
    return


def paint_bidder_status(emitter, bidder):
    claim = NU.from_nunits(bidder.available_claim)
    if claim > bidder.economics.maximum_allowed_locked:
        claim = f"{claim} (Above the allowed max. The bid will be partially refunded)"

    deposited_eth = bidder.get_deposited_eth
    bonus_eth = deposited_eth - bidder.economics.worklock_min_allowed_bid

    message = f"""
WorkLock Participant {bidder.checksum_address}
====================================================="""

    if bidder.has_claimed:
        message += f"""
Tokens Claimed? ...... Yes
Locked ETH ........... {prettify_eth_amount(bidder.get_deposited_eth)}"""
    else:
        message += f"""
Tokens Claimed? ...... No
Total Bid ............ {prettify_eth_amount(deposited_eth)}
    Base ETH ......... {prettify_eth_amount(bidder.economics.worklock_min_allowed_bid)}
    Bonus ETH ........ {prettify_eth_amount(bonus_eth)}
Tokens Allocated ..... {claim}"""

    compensation = bidder.available_compensation
    if compensation:
        message += f"""
Unspent Bid Amount ... {prettify_eth_amount(compensation)}"""

    message += f"""\n
Completed Work ....... {bidder.completed_work}
Available Refund ..... {prettify_eth_amount(bidder.available_refund)}

Refunded Work ........ {bidder.refunded_work}
Remaining Work ....... {bidder.remaining_work}
"""

    emitter.echo(message)
    return


def paint_bidding_notice(emitter, bidder):

    obligation = f"""
* WorkLock Participant Notice *
-------------------------------

- By participating in NuCypher's WorkLock you are committing to operating a staking
  NuCypher node after the bidding window closes.

- WorkLock token rewards are claimed in the form of a stake and will be locked for
  the stake duration.

- WorkLock ETH deposits will be available for refund at a rate of {prettify_eth_amount(bidder.worklock_agent.get_bonus_refund_rate())} 
  per confirmed period. This rate may vary until {maya.MayaDT(bidder.economics.bidding_end_date).local_datetime()}.

- Once claiming WorkLock tokens, you are obligated to maintain a networked and available
  Ursula-Worker node bonded to the staker address {bidder.checksum_address}
  for the duration of the stake(s) ({bidder.economics.worklock_commitment_duration} periods).

- Allow NuCypher network users to carry out uninterrupted re-encryption work orders
  at-will without interference. Failure to keep your node online, or violation of
  re-encryption work orders will result in the loss of staked tokens as described
  in the NuCypher slashing protocol.

- Keeping your Ursula node online during the staking period and correctly servicing
  re-encryption work orders will result in rewards paid out in ethers retro-actively
  and on-demand.

Accept WorkLock terms and node operator obligation?"""  # TODO: Show a special message for first bidder, since there's no refund rate yet?

    emitter.echo(obligation)
    return
