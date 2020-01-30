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
from web3 import Web3

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency, WorkLockAgent
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import WORKLOCK_BANNER
from nucypher.cli.actions import select_client_account
from nucypher.cli.commands.status import group_registry_options
from nucypher.cli.config import group_general_config
from nucypher.cli.options import option_force, group_options, option_checksum_address
from nucypher.cli.painting import (
    paint_receipt_summary,
    paint_worklock_status,
    paint_bidding_notice,
    paint_bidder_status,
    paint_worklock_claim
)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS

option_bidder_address = click.option('--bidder-address',
                                     help="Bidder's checksum address.",
                                     type=EIP55_CHECKSUM_ADDRESS)


def _setup_emitter(general_config):
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(WORKLOCK_BANNER)
    return emitter


class WorkLockOptions:

    __option_name__ = 'worklock_options'

    def __init__(self, bidder_address: str):
        self.bidder_address = bidder_address

    def create_bidder(self, registry):
        bidder = Bidder(checksum_address=self.bidder_address, registry=registry)
        return bidder


group_worklock_options = group_options(
    WorkLockOptions,
    bidder_address=option_bidder_address)


@click.group()
def worklock():
    """
    Manage stakes and other staker-related operations.
    """
    pass


@worklock.command()
@group_registry_options
@group_worklock_options
@group_general_config
def status(general_config, registry_options, worklock_options):
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    paint_worklock_status(emitter=emitter, registry=registry)
    if worklock_options.bidder_address:
        bidder = worklock_options.create_bidder(registry=registry)
        paint_bidder_status(emitter=emitter, bidder=bidder)
    return  # Exit


@worklock.command()
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
@click.option('--value', help="Eth value of bid", type=click.INT)
def bid(general_config, worklock_options, registry_options, force, value):
    emitter = _setup_emitter(general_config)
    if not value:
        if force:
            raise click.MissingParameter("Missing --value.")
        value = int(Web3.fromWei(click.prompt("Enter bid amount in ETH", type=click.FloatRange(min=0)), 'wei'))

    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    registry = registry_options.get_registry(emitter, general_config.debug)
    bidder = worklock_options.create_bidder(registry=registry)

    if not force:
        paint_bidding_notice(emitter=emitter, bidder=bidder)
        click.confirm(f"Place WorkLock bid of {Web3.fromWei(value, 'ether')} ETH?", abort=True)

    receipt = bidder.place_bid(value=value)
    emitter.message("Publishing WorkLock Bid...")

    # Ensure the total bid value is worth a claim that is at
    # least large enough for the minimum stake.
    minimum = bidder.economics.minimum_allowed_locked
    available_claim = bidder.available_claim
    if available_claim < minimum:
        warning = f"Total bid is too small for a claim, please bid more or cancel. " \
                  f"{available_claim} total / {minimum} minimum" \
                  f"(Total must be worth at least {NU.from_nunits(minimum)})"
        emitter.echo(warning, color='yellow')
    else:
        message = f'Current bid: {bidder.get_deposited_eth} | ' \
                  f'Available Claim: {bidder.available_claim} |' \
                  f'Note that available claim value may fluctuate ' \
                  f'until bidding closes and claims are finalized.'
        emitter.echo(message, color='yellow')

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
def cancel_bid(general_config, registry_options, worklock_options, force):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    registry = registry_options.get_registry(emitter, general_config.debug)
    bidder = worklock_options.create_bidder(registry=registry)
    if not force:
        value = bidder.get_deposited_eth
        click.confirm(f"Confirm bid cancellation of {Web3.fromWei(value, 'ether')} ETH"
                      f" for {worklock_options.bidder_address}?", abort=True)
    receipt = bidder.cancel_bid()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
def claim(general_config, worklock_options, registry_options, force):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    if not force:
        emitter.message("Note: Claiming WorkLock NU tokens will initialize a new stake.", color='blue')
        click.confirm(f"Continue worklock claim for bidder {worklock_options.bidder_address}?", abort=True)
    emitter.message("Submitting Claim...")
    registry = registry_options.get_registry(emitter, general_config.debug)
    bidder = worklock_options.create_bidder(registry=registry)
    receipt = bidder.claim()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    paint_worklock_claim(emitter, bidder_address=worklock_options.bidder_address)
    return  # Exit


@worklock.command()
@group_worklock_options
@group_registry_options
@group_general_config
def remaining_work(general_config, worklock_options, registry_options):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter, provider_uri=general_config.provider_uri)
    registry = registry_options.get_registry(emitter, general_config.debug)
    bidder = worklock_options.create_bidder(registry=registry)
    _remaining_work = bidder.remaining_work
    emitter.message(f"Work Remaining for {worklock_options.bidder_address}: {_remaining_work}")
    return  # Exit


@worklock.command()
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
def refund(general_config, worklock_options, registry_options, force):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter, provider_uri=general_config.provider_uri)
    if not force:
        click.confirm(f"Collect ETH refund for bidder {worklock_options.bidder_address}?", abort=True)
    emitter.message("Submitting WorkLock refund request...")
    registry = registry_options.get_registry(emitter, general_config.debug)
    bidder = worklock_options.create_bidder(registry=registry)
    receipt = bidder.refund_deposit()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@group_registry_options
@group_general_config
@option_checksum_address
def burn_unclaimed_tokens(general_config, registry_options, checksum_address):
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)
    if not checksum_address:
        checksum_address = select_client_account(emitter=emitter, provider_uri=general_config.provider_uri)
    receipt = worklock_agent.burn_unclaimed(sender_address=checksum_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    return  # Exit
