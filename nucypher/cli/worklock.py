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

from nucypher.blockchain.eth.agents import ContractAgency, WorkLockAgent
from nucypher.characters.banners import WORKLOCK_BANNER
from nucypher.cli.actions import select_client_account
from nucypher.cli.common_options import option_force, group_options, option_checksum_address
from nucypher.cli.config import group_general_config
from nucypher.cli.painting import (
    paint_receipt_summary,
    paint_worklock_status,
    paint_worklock_participant_notice,
    paint_worklock_participant_status,
    paint_worklock_claim
)
from nucypher.cli.status import group_registry_options
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS

option_bidder_address = click.option('--bidder-address',
                                     help="Bidder's checksum address.",
                                     type=EIP55_CHECKSUM_ADDRESS)

option_allocation_address = click.option('--allocation-address',
                                         help="Worklock allocation contract address",
                                         type=EIP55_CHECKSUM_ADDRESS)


def _setup_emitter(general_config):
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(WORKLOCK_BANNER)
    return emitter


class WorkLockOptions:

    __option_name__ = 'worklock_options'

    def __init__(self, bidder_address, allocation_address):
        self.bidder_address = bidder_address
        self.allocation_address = allocation_address

    def create_agent(self, registry):
        agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)
        return agent


group_worklock_options = group_options(
    WorkLockOptions,
    bidder_address=option_bidder_address,
    allocation_address=option_allocation_address)


@click.group()
def worklock():
    """
    Manage stakes and other staker-related operations.
    """
    pass


@worklock.command(name='status')
@group_registry_options
@group_worklock_options
@group_general_config
def status(general_config, registry_options, worklock_options):
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    paint_worklock_status(emitter=emitter, registry=registry)
    if worklock_options.bidder_address:
        paint_worklock_participant_status(emitter=emitter,
                                          registry=registry,
                                          bidder_address=worklock_options.bidder_address)
    return  # Exit


@worklock.command(name='bid')
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
@click.option('--value', help="Eth value of bid", type=click.INT)
def bid(general_config, worklock_options, registry_options, force, value):
    emitter = _setup_emitter(general_config)
    if not value:
        value = int(Web3.fromWei(click.prompt("Enter bid amount in ETH", type=click.FloatRange(min=0)), 'wei'))
        if force:
            raise click.MissingParameter("Missing --value.")
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    registry = registry_options.get_registry(emitter, general_config.debug)
    worklock_agent = worklock_options.create_agent(registry=registry)

    if not force:
        paint_worklock_participant_notice(emitter=emitter, bidder_address=worklock_options.bidder_address, registry=registry)
        click.confirm(f"Place WorkLock bid of {Web3.fromWei(value, 'ether')} ETH?", abort=True)

    receipt = worklock_agent.bid(bidder_address=worklock_options.bidder_address, value=value)
    emitter.message("Publishing WorkLock Bid...")
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command(name='cancel-bid')
@group_registry_options
@group_worklock_options
@group_general_config
def burn_unclaimed_tokens(general_config, registry_options, worklock_options):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    registry = registry_options.get_registry(emitter, general_config.debug)
    worklock_agent = worklock_options.create_agent(registry=registry)
    receipt = worklock_agent.cancel_bid(bidder_address=worklock_options.bidder_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command(name='claim')
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
    worklock_agent = worklock_options.create_agent(registry=registry)
    receipt = worklock_agent.claim(bidder_address=worklock_options.bidder_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    allocation_address = worklock_agent.get_allocation_from_bidder(bidder_address=worklock_options.bidder_address)
    paint_worklock_claim(emitter, bidder_address=worklock_options.bidder_address, allocation_address=allocation_address)
    return  # Exit


@worklock.command(name='remaining-work')
@group_worklock_options
@group_registry_options
@group_general_config
def remaining_work(general_config, worklock_options, registry_options):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    registry = registry_options.get_registry(emitter, general_config.debug)
    worklock_agent = worklock_options.create_agent(registry=registry)
    _remaining_work = worklock_agent.get_remaining_work(bidder_address=worklock_options.bidder_address)
    emitter.message(f"Work Remaining for {worklock_options.bidder_address}: {_remaining_work}")
    return  # Exit


@worklock.command(name='refund')
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
def refund(general_config, worklock_options, registry_options, force):
    emitter = _setup_emitter(general_config)
    if not worklock_options.bidder_address:
        worklock_options.bidder_address = select_client_account(emitter=emitter,
                                                                provider_uri=general_config.provider_uri)
    if not force:
        click.confirm(f"Collect ETH refund for bidder {worklock_options.bidder_address}?", abort=True)
    emitter.message("Submitting WorkLock refund request...")
    registry = registry_options.get_registry(emitter, general_config.debug)
    worklock_agent = worklock_options.create_agent(registry=registry)
    receipt = worklock_agent.refund(beneficiary_address=worklock_options.bidder_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command(name='burn-unclaimed-tokens')
@group_registry_options
@group_worklock_options
@group_general_config
@option_checksum_address
def burn_unclaimed_tokens(general_config, registry_options, worklock_options, checksum_address):
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    worklock_agent = worklock_options.create_agent(registry=registry)
    if not checksum_address:
        checksum_address = select_client_account(emitter=emitter, provider_uri=general_config.provider_uri)
    receipt = worklock_agent.burn_unclaimed(sender_address=checksum_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    return  # Exit
