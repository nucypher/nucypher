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
from decimal import Decimal
from typing import Optional

import click
import maya
import tabulate
from web3 import Web3

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency, WorkLockAgent
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import prettify_eth_amount
from nucypher.characters.banners import WORKLOCK_BANNER
from nucypher.cli.actions import get_client_password
from nucypher.cli.actions import select_client_account
from nucypher.cli.commands.status import group_registry_options
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    option_force,
    group_options,
    option_hw_wallet,
    option_signer_uri
)
from nucypher.cli.painting import (
    paint_receipt_summary,
    paint_worklock_status,
    paint_bidding_notice,
    paint_bidder_status,
    paint_worklock_claim
)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, DecimalRange

option_bidder_address = click.option('--bidder-address',
                                     help="Bidder's checksum address.",
                                     type=EIP55_CHECKSUM_ADDRESS)


def _setup_emitter(general_config):
    emitter = general_config.emitter
    emitter.banner(WORKLOCK_BANNER)
    return emitter


class WorkLockOptions:

    __option_name__ = 'worklock_options'

    def __init__(self, bidder_address: str, signer_uri):
        self.bidder_address = bidder_address
        self.signer_uri = signer_uri

    def __create_bidder(self,
                        registry,
                        signer: Optional[Signer] = None,
                        transacting: bool = True,
                        hw_wallet: bool = False):
        client_password = None
        if transacting and not signer and not hw_wallet:
            client_password = get_client_password(checksum_address=self.bidder_address)
        bidder = Bidder(checksum_address=self.bidder_address,
                        registry=registry,
                        client_password=client_password,
                        signer=signer,
                        transacting=transacting)
        return bidder

    def create_bidder(self, registry, hw_wallet: bool = False):
        signer = Signer.from_signer_uri(self.signer_uri) if self.signer_uri else None
        return self.__create_bidder(registry=registry, signer=signer, hw_wallet=hw_wallet, transacting=True)

    def create_transactionless_bidder(self, registry):
        return self.__create_bidder(registry, transacting=False)


group_worklock_options = group_options(
    WorkLockOptions,
    bidder_address=option_bidder_address,
    signer_uri=option_signer_uri
)


@click.group()
def worklock():
    """
    Participate in NuCypher's WorkLock to obtain NU tokens
    """
    pass


@worklock.command()
@group_registry_options
@group_worklock_options
@group_general_config
def status(general_config, registry_options, worklock_options):
    """Show current WorkLock information"""

    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    paint_worklock_status(emitter=emitter, registry=registry)
    if worklock_options.bidder_address:
        bidder = worklock_options.create_transactionless_bidder(registry=registry)
        paint_bidder_status(emitter=emitter, bidder=bidder)
    return  # Exit


@worklock.command()
@group_general_config
@group_registry_options
@group_worklock_options
@option_force
@option_hw_wallet
@click.option('--value', help="ETH value of bid", type=DecimalRange(min=0))
def bid(general_config, worklock_options, registry_options, force, hw_wallet, value):
    """Place a bid, or increase an existing bid"""
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    now = maya.now().epoch
    if not worklock_agent.start_bidding_date <= now <= worklock_agent.end_bidding_date:
        raise click.Abort(f"You can't bid, the bidding window is closed.")

    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=registry_options.provider_uri,
                                                                poa=registry_options.poa,
                                                                network=registry_options.network,
                                                                registry=registry,
                                                                show_balances=True)

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
    return  # Exit


@worklock.command()
@group_general_config
@group_registry_options
@group_worklock_options
@option_force
@option_hw_wallet
def cancel_bid(general_config, registry_options, worklock_options, force, hw_wallet):
    """Cancel your bid and receive your ETH back"""
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    now = maya.now().epoch
    if not worklock_agent.start_bidding_date <= now <= worklock_agent.end_cancellation_date:
        raise click.Abort(f"You can't cancel your bid. The cancellation window is closed.")

    if not worklock_options.bidder_address:  # TODO: Consider bundle this in worklock_options
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=registry_options.provider_uri,
                                                                poa=registry_options.poa,
                                                                network=registry_options.network,
                                                                show_balances=True,
                                                                registry=registry)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)
    if not force:
        value = bidder.get_deposited_eth
        click.confirm(f"Confirm bid cancellation of {prettify_eth_amount(value)}"
                      f" for {worklock_options.bidder_address}?", abort=True)
    receipt = bidder.cancel_bid()
    emitter.echo("Bid canceled\n", color='green')
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@option_force
@option_hw_wallet
@group_registry_options
@group_worklock_options
@group_general_config
def claim(general_config, worklock_options, registry_options, force, hw_wallet):
    """Claim tokens for your bid, and start staking them"""
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    if not worklock_agent.is_claiming_available():
        raise click.Abort(f"You can't claim tokens. Claiming is not currently available.")

    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=registry_options.provider_uri,
                                                                poa=registry_options.poa,
                                                                network=registry_options.network,
                                                                registry=registry,
                                                                show_balances=True)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    unspent_bid = bidder.available_compensation
    if unspent_bid:
        emitter.echo(f"Note that WorkLock did not use your entire bid due to a maximum claim limit.\n"
                     f"Therefore, an unspent amount of {prettify_eth_amount(unspent_bid)} is available for refund.")
        if not force:
            click.confirm(f"Before claiming your NU tokens for {worklock_options.bidder_address}, you will need to be refunded your unspent bid amount. Would you like to proceed?", abort=True)
        emitter.echo("Requesting refund of unspent bid amount...")
        receipt = bidder.withdraw_compensation()
        paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)

    has_claimed = bidder._has_claimed
    if has_claimed:
        emitter.echo(f"Claim was already done for {bidder.checksum_address}", color='red')
        return

    tokens = NU.from_nunits(bidder.available_claim)
    emitter.echo(f"\nYou have an available claim of {tokens} 🎉 \n", color='green', bold=True)
    if not force:
        lock_duration = bidder.worklock_agent.worklock_parameters()[-2]
        emitter.echo(f"Note: Claiming WorkLock NU tokens will initialize a new stake to be locked for {lock_duration} periods.",
                     color='blue')
        click.confirm(f"Continue WorkLock claim for bidder {worklock_options.bidder_address}?", abort=True)
    emitter.echo("Submitting Claim...")

    receipt = bidder.claim()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    paint_worklock_claim(emitter=emitter,
                         bidder_address=worklock_options.bidder_address,
                         network=registry_options.network,
                         provider_uri=registry_options.provider_uri)
    return  # Exit


@worklock.command()
@group_worklock_options
@group_registry_options
@group_general_config
def remaining_work(general_config, worklock_options, registry_options):
    """Check how much work is pending until you can get all your locked ETH back"""
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=registry_options.provider_uri,
                                                                poa=registry_options.poa,
                                                                network=registry_options.network,
                                                                registry=registry,
                                                                show_balances=True)

    bidder = worklock_options.create_transactionless_bidder(registry=registry)
    _remaining_work = bidder.remaining_work
    emitter.echo(f"Work Remaining for {worklock_options.bidder_address}: {_remaining_work}")
    return  # Exit


@worklock.command()
@option_force
@option_hw_wallet
@group_registry_options
@group_worklock_options
@group_general_config
def refund(general_config, worklock_options, registry_options, force, hw_wallet):
    """Reclaim ETH unlocked by your work"""
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=registry_options.provider_uri,
                                                                poa=registry_options.poa,
                                                                network=registry_options.network,
                                                                registry=registry,
                                                                show_balances=True)
    if not force:
        click.confirm(f"Collect ETH refund for bidder {worklock_options.bidder_address}?", abort=True)
    emitter.echo("Submitting WorkLock refund request...")

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)
    receipt = bidder.refund_deposit()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@group_general_config
@group_registry_options
@group_worklock_options
@option_force
@option_hw_wallet
@click.option('--gas-limit', help="Gas limit per each verification transaction", type=click.IntRange(min=60000))
# TODO: Consider moving to administrator (nucypher-deploy) #1758
def enable_claiming(general_config, registry_options, worklock_options, force, hw_wallet, gas_limit):
    """Ensure correctness of bidding and enable claiming"""
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    if not worklock_options.bidder_address:  # TODO: Consider bundle this in worklock_options
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=registry_options.provider_uri,
                                                                network=registry_options.network,
                                                                registry=registry,
                                                                show_balances=True)
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
        emitter.echo(f"At least {len(whales)} bidders got a force refund\n", color='green')

        paint_receipt_summary(receipt=force_refund_receipt,
                              emitter=emitter,
                              chain_name=bidder.staking_agent.blockchain.client.chain_name,
                              transaction_type=f"force-refund")
    else:
        emitter.echo(f"All bids are correct, force refund is not needed\n", color='yellow')

    if not bidder.worklock_agent.bidders_checked():
        if not gas_limit:
            # TODO print gas estimations
            min_gas = 180000
            gas_limit = click.prompt(f"Enter gas limit per each verification transaction (at least {min_gas})",
                                     type=click.IntRange(min=min_gas))

        if not force:
            click.confirm(f"Confirm verifying of bidding from {worklock_options.bidder_address} "
                          f"using {gas_limit} gas per each transaction?", abort=True)

        verification_receipts = bidder.verify_bidding_correctness(gas_limit=gas_limit)
        emitter.echo("Bidding has been checked\n", color='green')

        for iteration, receipt in verification_receipts.items():
            paint_receipt_summary(receipt=receipt,
                                  emitter=emitter,
                                  chain_name=bidder.staking_agent.blockchain.client.chain_name,
                                  transaction_type=f"verify-correctness[{iteration}]")
    else:
        emitter.echo(f"Bidders have already been checked\n", color='yellow')

    return  # Exit
