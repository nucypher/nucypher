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
import maya
import os
import tabulate
from decimal import Decimal
from typing import Optional
from web3 import Web3

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency, WorkLockAgent
from nucypher.blockchain.eth.signers import Signer, ClefSigner
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import prettify_eth_amount
from nucypher.cli.actions.auth import get_client_password
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.utils import connect_to_blockchain, get_registry, setup_emitter
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import (
    AVAILABLE_CLAIM_NOTICE,
    BIDDERS_ALREADY_VERIFIED,
    BIDDING_WINDOW_CLOSED,
    BIDS_VALID_NO_FORCE_REFUND_INDICATED,
    CLAIM_ALREADY_PLACED,
    COMPLETED_BID_VERIFICATION,
    CONFIRM_BID_VERIFICATION,
    CONFIRM_COLLECT_WORKLOCK_REFUND,
    CONFIRM_REQUEST_WORKLOCK_COMPENSATION,
    CONFIRM_WORKLOCK_CLAIM,
    PROMPT_BID_VERIFY_GAS_LIMIT,
    REQUESTING_WORKLOCK_COMPENSATION,
    SUBMITTING_WORKLOCK_CLAIM,
    SUBMITTING_WORKLOCK_REFUND_REQUEST,
    SUCCESSFUL_BID_CANCELLATION,
    VERIFICATION_ESTIMATES,
    WHALE_WARNING,
    WORKLOCK_ADDITIONAL_COMPENSATION_AVAILABLE,
    WORKLOCK_CLAIM_ADVISORY
)
from nucypher.cli.options import (
    group_options,
    option_force,
    option_hw_wallet,
    option_network,
    option_provider_uri,
    option_registry_filepath,
    option_signer_uri
)
from nucypher.cli.painting.transactions import paint_receipt_summary
from nucypher.cli.painting.worklock import (
    paint_bidder_status,
    paint_bidding_notice,
    paint_worklock_claim,
    paint_worklock_status
)
from nucypher.cli.types import DecimalRange, EIP55_CHECKSUM_ADDRESS
from nucypher.config.constants import NUCYPHER_ENVVAR_PROVIDER_URI

option_bidder_address = click.option('--bidder-address',
                                     help="Bidder's checksum address.",
                                     type=EIP55_CHECKSUM_ADDRESS)


class WorkLockOptions:

    __option_name__ = 'worklock_options'

    def __init__(self,
                 bidder_address: str,
                 signer_uri: str,
                 provider_uri: str,
                 registry_filepath: str,
                 network: str):

        self.bidder_address = bidder_address
        self.signer_uri = signer_uri
        self.provider_uri = provider_uri
        self.registry_filepath = registry_filepath
        self.network = network

    def setup(self, general_config) -> tuple:
        emitter = setup_emitter(general_config)   # TODO: Restore Banner:  network=self.network.capitalize()
        registry = get_registry(network=self.network, registry_filepath=self.registry_filepath)
        blockchain = connect_to_blockchain(emitter=emitter, provider_uri=self.provider_uri)
        return emitter, registry, blockchain

    def __create_bidder(self,
                        registry,
                        transacting: bool = True,
                        hw_wallet: bool = False) -> Bidder:

        client_password = None
        is_clef = ClefSigner.is_valid_clef_uri(self.signer_uri)
        if transacting and not is_clef and not hw_wallet:
            client_password = get_client_password(checksum_address=self.bidder_address)
        signer = Signer.from_signer_uri(self.signer_uri) if self.signer_uri else None
        bidder = Bidder(checksum_address=self.bidder_address,
                        registry=registry,
                        client_password=client_password,
                        signer=signer,
                        transacting=transacting)
        return bidder

    def create_bidder(self, registry, hw_wallet: bool = False):
        return self.__create_bidder(registry=registry, hw_wallet=hw_wallet, transacting=True)

    def create_transactionless_bidder(self, registry):
        return self.__create_bidder(registry, transacting=False)


group_worklock_options = group_options(
    WorkLockOptions,
    bidder_address=option_bidder_address,
    signer_uri=option_signer_uri,
    provider_uri=option_provider_uri(required=True, default=os.environ.get(NUCYPHER_ENVVAR_PROVIDER_URI)),
    network=option_network(required=True),
    registry_filepath=option_registry_filepath,
)


@click.group()
def worklock():
    """Participate in NuCypher's WorkLock to obtain NU tokens"""


@worklock.command()
@group_worklock_options
@group_general_config
def status(general_config, worklock_options):
    """Show current WorkLock information"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    paint_worklock_status(emitter=emitter, registry=registry)
    if worklock_options.bidder_address:
        bidder = worklock_options.create_transactionless_bidder(registry=registry)
        paint_bidder_status(emitter=emitter, bidder=bidder)


@worklock.command()
@group_general_config
@group_worklock_options
@option_force
@option_hw_wallet
@click.option('--value', help="ETH value of bid", type=DecimalRange(min=0))
def bid(general_config, worklock_options, force, hw_wallet, value):
    """Place a bid, or increase an existing bid"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    now = maya.now().epoch
    if not worklock_agent.start_bidding_date <= now <= worklock_agent.end_bidding_date:
        emitter.echo(BIDDING_WINDOW_CLOSED, color='red')
        raise click.Abort()

    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=worklock_options.provider_uri,
                                                                poa=worklock_options.poa,
                                                                network=worklock_options.network,
                                                                registry=registry,
                                                                show_eth_balance=True)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    if not value:
        if force:
            raise click.MissingParameter("Missing --value.")

        existing_bid_amount = bidder.get_deposited_eth
        if not existing_bid_amount:  # It's the first bid
            minimum_bid = bidder.worklock_agent.minimum_allowed_bid
            minimum_bid_in_eth = Web3.fromWei(minimum_bid, 'ether')
            prompt = f"Enter bid amount in ETH (at least {minimum_bid_in_eth} ETH)"
        else:  # There's an existing bid and the bidder is increasing the amount
            emitter.message(f"You have an existing bid of {Web3.fromWei(existing_bid_amount, 'ether')} ETH")
            minimum_bid_in_eth = Web3.fromWei(1, 'ether')
            prompt = f"Enter the amount in ETH that you want to increase your bid"
        value = click.prompt(prompt, type=DecimalRange(min=minimum_bid_in_eth))

    value = int(Web3.toWei(Decimal(value), 'ether'))

    if not force:
        paint_bidding_notice(emitter=emitter, bidder=bidder)
        click.confirm(f"Place WorkLock bid of {prettify_eth_amount(value)}?", abort=True)

    receipt = bidder.place_bid(value=value)
    emitter.message("Publishing WorkLock Bid...")

    maximum = NU.from_nunits(bidder.economics.maximum_allowed_locked)
    available_claim = NU.from_nunits(bidder.available_claim)
    message = f'Current bid: {prettify_eth_amount(bidder.get_deposited_eth)} | Claim: {available_claim}\n'
    if available_claim > maximum:
        message += f"This claim is currently above the allowed max ({maximum}), so the bid may be partially refunded.\n"
    message += f'Note that available claim value may fluctuate until bidding closes and claims are finalized.\n'
    emitter.echo(message, color='yellow')

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)


@worklock.command()
@group_general_config
@group_worklock_options
@option_force
@option_hw_wallet
def cancel_bid(general_config, worklock_options, force, hw_wallet):
    """Cancel your bid and receive your ETH back"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    now = maya.now().epoch
    if not worklock_agent.start_bidding_date <= now <= worklock_agent.end_cancellation_date:
        raise click.Abort(f"You can't cancel your bid. The cancellation window is closed.")

    if not worklock_options.bidder_address:  # TODO: Consider bundle this in worklock_options
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=worklock_options.provider_uri,
                                                                poa=worklock_options.poa,
                                                                network=worklock_options.network,
                                                                show_eth_balance=True,
                                                                registry=registry)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)
    if not force:
        value = bidder.get_deposited_eth
        click.confirm(f"Confirm bid cancellation of {prettify_eth_amount(value)}"
                      f" for {worklock_options.bidder_address}?", abort=True)
    receipt = bidder.cancel_bid()
    emitter.echo(SUCCESSFUL_BID_CANCELLATION, color='green')
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@option_force
@option_hw_wallet
@group_worklock_options
@group_general_config
def claim(general_config, worklock_options, force, hw_wallet):
    """Claim tokens for your bid, and start staking them"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    if not worklock_agent.is_claiming_available():
        raise click.Abort(f"You can't claim tokens. Claiming is not currently available.")

    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=worklock_options.provider_uri,
                                                                poa=worklock_options.poa,
                                                                network=worklock_options.network,
                                                                registry=registry,
                                                                show_eth_balance=True)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    unspent_bid = bidder.available_compensation
    if unspent_bid:
        emitter.echo(WORKLOCK_ADDITIONAL_COMPENSATION_AVAILABLE.format(amount=prettify_eth_amount(unspent_bid)))
        if not force:
            message = CONFIRM_REQUEST_WORKLOCK_COMPENSATION.format(bidder_address=worklock_options.bidder_address)
            click.confirm(message, abort=True)
        emitter.echo(REQUESTING_WORKLOCK_COMPENSATION)
        receipt = bidder.withdraw_compensation()
        paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)

    has_claimed = bidder.has_claimed
    if bool(has_claimed):
        emitter.echo(CLAIM_ALREADY_PLACED.format(bidder_address=bidder.checksum_address), color='red')
        return

    tokens = NU.from_nunits(bidder.available_claim)
    emitter.echo(AVAILABLE_CLAIM_NOTICE.format(tokens=tokens), color='green', bold=True)
    if not force:
        lock_duration = bidder.worklock_agent.worklock_parameters()[-2]
        emitter.echo(WORKLOCK_CLAIM_ADVISORY.format(lock_duration=lock_duration), color='blue')
        click.confirm(CONFIRM_WORKLOCK_CLAIM.format(bidder_address=worklock_options.bidder_address), abort=True)
    emitter.echo(SUBMITTING_WORKLOCK_CLAIM)

    receipt = bidder.claim()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    paint_worklock_claim(emitter=emitter,
                         bidder_address=worklock_options.bidder_address,
                         network=worklock_options.network,
                         provider_uri=worklock_options.provider_uri)


@worklock.command()
@group_worklock_options
@group_general_config
def remaining_work(general_config, worklock_options):
    """Check how much work is pending until you can get all your locked ETH back"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=worklock_options.provider_uri,
                                                                poa=worklock_options.poa,
                                                                network=worklock_options.network,
                                                                registry=registry,
                                                                show_eth_balance=True)

    bidder = worklock_options.create_transactionless_bidder(registry=registry)
    _remaining_work = bidder.remaining_work
    emitter.echo(f"Work Remaining for {worklock_options.bidder_address}: {_remaining_work}")


@worklock.command()
@option_force
@option_hw_wallet
@group_worklock_options
@group_general_config
def refund(general_config, worklock_options, force, hw_wallet):
    """Reclaim ETH unlocked by your work"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=worklock_options.provider_uri,
                                                                poa=worklock_options.poa,
                                                                network=worklock_options.network,
                                                                registry=registry,
                                                                show_eth_balance=True)
    if not force:
        click.confirm(CONFIRM_COLLECT_WORKLOCK_REFUND.format(bidder_Address=worklock_options.bidder_address), abort=True)
    emitter.echo(SUBMITTING_WORKLOCK_REFUND_REQUEST)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)
    receipt = bidder.refund_deposit()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)


@worklock.command()
@group_general_config
@group_worklock_options
@option_force
@option_hw_wallet
@click.option('--gas-limit', help="Gas limit per each verification transaction", type=click.IntRange(min=60000))
# TODO: Consider moving to administrator (nucypher-deploy) #1758
def enable_claiming(general_config, worklock_options, force, hw_wallet, gas_limit):
    """Ensure correctness of bidding and enable claiming"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    if not worklock_options.bidder_address:  # TODO: Consider bundle this in worklock_options
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=worklock_options.provider_uri,
                                                                network=worklock_options.network,
                                                                registry=registry,
                                                                show_eth_balance=True)
    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    whales = bidder.get_whales()
    if whales:
        headers = ("Bidders that require correction", "Current bid bonus")
        columns = (whales.keys(), map(prettify_eth_amount, whales.values()))
        emitter.echo(tabulate.tabulate(dict(zip(headers, columns)), headers=headers, floatfmt="fancy_grid"))

        if not force:
            click.confirm(f"Confirm force refund to at least {len(whales)} bidders"
                          f" using {worklock_options.bidder_address}?", abort=True)

        force_refund_receipt = bidder.force_refund()
        emitter.echo(WHALE_WARNING.format(number=len(whales)), color='green')

        paint_receipt_summary(receipt=force_refund_receipt,
                              emitter=emitter,
                              chain_name=bidder.staking_agent.blockchain.client.chain_name,
                              transaction_type=f"force-refund")
    else:
        emitter.echo(BIDS_VALID_NO_FORCE_REFUND_INDICATED, color='yellow')

    if not bidder.worklock_agent.bidders_checked():

        confirmation = gas_limit and force
        while not confirmation:
            if not gas_limit:
                min_gas = 180000
                gas_limit = click.prompt(PROMPT_BID_VERIFY_GAS_LIMIT.format(min_gas=min_gas), type=click.IntRange(min=min_gas))

            bidders_per_transaction = bidder.worklock_agent.estimate_verifying_correctness(gas_limit=gas_limit)

            if not force:
                message = CONFIRM_BID_VERIFICATION.format(bidder_address=worklock_options.bidder_address,
                                                          gas_limit=gas_limit,
                                                          bidders_per_transaction=bidders_per_transaction)
                confirmation = click.confirm(message)
                gas_limit = gas_limit if confirmation else None
            else:
                emitter.echo(VERIFICATION_ESTIMATES.format(gas_limit=gas_limit,
                                                           bidders_per_transaction=bidders_per_transaction))
                confirmation = True

        verification_receipts = bidder.verify_bidding_correctness(gas_limit=gas_limit)
        emitter.echo(COMPLETED_BID_VERIFICATION, color='green')

        for iteration, receipt in verification_receipts.items():
            paint_receipt_summary(receipt=receipt,
                                  emitter=emitter,
                                  chain_name=bidder.staking_agent.blockchain.client.chain_name,
                                  transaction_type=f"verify-correctness[{iteration}]")
    else:
        emitter.echo(BIDDERS_ALREADY_VERIFIED, color='yellow')
