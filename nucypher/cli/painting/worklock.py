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
from nucypher.cli.literature import SUCCESSFUL_WORKLOCK_CLAIM, WORKLOCK_AGREEMENT


def paint_bidding_notice(emitter, bidder):
    message = WORKLOCK_AGREEMENT.format(refund_rate=prettify_eth_amount(bidder.worklock_agent.get_bonus_refund_rate()),
                                        end_date=maya.MayaDT(bidder.economics.bidding_end_date).local_datetime(),
                                        bidder_address=bidder.checksum_address,
                                        duration=bidder.economics.worklock_commitment_duration)
    emitter.echo(message)
    return


def paint_worklock_claim(emitter, bidder_address: str, network: str, provider_uri: str):
    message = SUCCESSFUL_WORKLOCK_CLAIM.format(bidder_address=bidder_address,
                                               network=network, 
                                               provider_uri=provider_uri)
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

    emitter.echo(f"\nWorkLock ({worklock_agent.contract_address})", bold=True, color='green')

    payload = f"""
Time
══════════════════════════════════════════════════════

Escrow Period ({'Open' if bidding_open else 'Closed'})
------------------------------------------------------
Allocations Available . {'Yes' if worklock_agent.is_claiming_available() else 'No'}
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
Min. Allowed Escrow ... {prettify_eth_amount(worklock_agent.minimum_allowed_bid)}
Participants .......... {worklock_agent.get_bidders_population()}
ETH Supply ............ {prettify_eth_amount(worklock_agent.get_eth_supply())}
ETH Pool .............. {prettify_eth_amount(blockchain.client.get_balance(worklock_agent.contract_address))}

Base (minimum escrow)
------------------------------------------------------
Base Deposit Rate ..... {worklock_agent.get_base_deposit_rate()} NU per base ETH

Bonus (surplus over minimum escrow)
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


def paint_bidder_status(emitter, bidder):
    claim = NU.from_nunits(bidder.available_claim)
    if claim > bidder.economics.maximum_allowed_locked:
        claim = f"{claim} (Above the allowed max. The escrow will be partially refunded)"

    deposited_eth = bidder.get_deposited_eth
    bonus_eth = deposited_eth - bidder.economics.worklock_min_allowed_bid

    message = f"""
WorkLock Participant {bidder.checksum_address}
══════════════════════════════════════════════════════"""

    if bidder.has_claimed:
        message += f"""
NU Claimed? ............ Yes
Locked ETH ............. {prettify_eth_amount(bidder.get_deposited_eth)}"""
    else:
        message += f"""
NU Claimed? ............ No
Total Escrow ........... {prettify_eth_amount(deposited_eth)}
    Base ETH ........... {prettify_eth_amount(bidder.economics.worklock_min_allowed_bid)}
    Bonus ETH .......... {prettify_eth_amount(bonus_eth)}
NU Allocated ........... {claim}"""

    compensation = bidder.available_compensation
    if compensation:
        message += f"""
Unspent Escrow Amount .. {prettify_eth_amount(compensation)}"""

    message += f"""\n
Completed Work ......... {bidder.completed_work}
Available Refund ....... {prettify_eth_amount(bidder.available_refund)}

Refunded Work .......... {bidder.refunded_work}
Remaining Work ......... {bidder.remaining_work}
"""

    emitter.echo(message)
