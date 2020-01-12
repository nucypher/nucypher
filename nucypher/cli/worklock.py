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
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import LocalContractRegistry, InMemoryContractRegistry
from nucypher.characters.banners import WORKLOCK_BANNER
from nucypher.cli.common_options import option_force, option_config_root, group_options
from nucypher.cli.config import group_general_config
from nucypher.cli.painting import paint_receipt_summary, paint_worklock_status, paint_worklock_participant_notice
from nucypher.cli.status import group_registry_options
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS

option_bidder_address = click.option('--bidder-address', help="Bidder's checksum address.", type=EIP55_CHECKSUM_ADDRESS)
option_allocation_address = click.option('--allocation-address', help="Worklock allocation contract address", type=EIP55_CHECKSUM_ADDRESS)


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

    def create_agent(self, registry_filepath):
        if registry_filepath:
            registry = LocalContractRegistry(filepath=registry_filepath)
        else:
            registry = InMemoryContractRegistry.from_latest_publication()
        agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)
        return agent

    def get_blockchain(self):
        return BlockchainInterfaceFactory.get_interface(provider_uri=self.config_options.provider_uri)  # Eager connection


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
@group_general_config
def status(general_config, registry_options):
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    paint_worklock_status(emitter=emitter, registry=registry)
    return  # Exit


@worklock.command(name='bid')
@option_force
@group_registry_options
@group_worklock_options
@group_general_config
@click.option('--value', help="Eth value of bid", type=click.INT)
def bid(general_config, worklock_options, registry_options, force, value, bidder_address):
    emitter = _setup_emitter(general_config)

    if not value:
        value = int(Web3.fromWei(click.prompt("Enter bid amount in ETH", type=click.FloatRange(min=0)), 'wei'))
        if force:
            raise click.MissingParameter("Missing --value.")

    registry = registry_options.get_registry()
    worklock_agent = worklock_options.create_agent(registry_filepath=registry.filepath)

    if not force:
        paint_worklock_participant_notice(emitter=emitter, bidder_address=bidder_address, registry=registry)
        click.confirm(f"Place WorkLock bid of {Web3.fromWei(value, 'ether')} ETH?", abort=True)
    receipt = worklock_agent.bid(bidder_address=bidder_address, value=value)
    emitter.message("Publishing WorkLock Bid...")

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=worklock_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command(name='claim')
@option_config_root
@option_force
@group_general_config
def claim(force):
    emitter = _setup_emitter(general_config)

    if not force:
        emitter.message("Note: Claiming WorkLock NU tokens will initialize a new stake.", color='blue')
        click.confirm(f"Continue worklock claim for bidder {bidder_address}?", abort=True)
    emitter.message("Submitting Claim...")
    receipt = WORKLOCK_AGENT.claim(sender_address=bidder_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)
    emitter.message("Successfully claimed WorkLock tokens."
                    "To create a new stakeholder run 'nucypher stake init-stakeholder' --provider <URI>"
                    "To bond a worker run 'nucypher stake set-worker' --worker-address <ADDRESS>", color='green')
    return  # Exit


@worklock.command(name='remaining-work')
@option_config_root
@option_force
@group_general_config
def remaining_work(force):
    emitter = _setup_emitter(general_config)

    remaining_work = WORKLOCK_AGENT.get_remaining_work(allocation_address=bidder_address)
    emitter.message(f"Work Remaining for {bidder_address}: {remaining_work}")
    return  # Exit


@worklock.command(name='refund')
@option_config_root
@option_force
@group_general_config
def refund(force):
    emitter = _setup_emitter(general_config)

    if not force:
        click.confirm(f"Collect ETH refund for bidder {bidder_address}?", abort=True)
    emitter.message("Submitting WorkLock refund request...")
    receipt = WORKLOCK_AGENT.refund(sender_address=bidder_address)
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)
    return  # Exit
