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

from eth_typing.evm import ChecksumAddress
from web3 import Web3

from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency, WorkLockAgent
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.signers import Signer, ClefSigner
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import prettify_eth_amount
from nucypher.cli.actions.auth import get_client_password
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.utils import connect_to_blockchain, get_registry, setup_emitter
from nucypher.cli.config import group_general_config, GroupGeneralConfig
from nucypher.cli.literature import (
    AVAILABLE_CLAIM_NOTICE,
    BID_AMOUNT_PROMPT_WITH_MIN_BID,
    BID_INCREASE_AMOUNT_PROMPT,
    BIDDERS_ALREADY_VERIFIED,
    BIDDING_WINDOW_CLOSED,
    BIDS_VALID_NO_FORCE_REFUND_INDICATED,
    CANCELLATION_WINDOW_CLOSED,
    CLAIM_ALREADY_PLACED,
    CLAIMING_NOT_AVAILABLE,
    COMPLETED_BID_VERIFICATION,
    CONFIRM_BID_VERIFICATION,
    CONFIRM_COLLECT_WORKLOCK_REFUND,
    CONFIRM_REQUEST_WORKLOCK_COMPENSATION,
    CONFIRM_WORKLOCK_CLAIM,
    EXISTING_BID_AMOUNT_NOTICE,
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
    option_signer_uri,
    option_participant_address)
from nucypher.cli.painting.transactions import paint_receipt_summary
from nucypher.cli.painting.worklock import (
    paint_bidder_status,
    paint_bidding_notice,
    paint_worklock_claim,
    paint_worklock_status
)
from nucypher.cli.types import DecimalRange, EIP55_CHECKSUM_ADDRESS
from nucypher.config.constants import NUCYPHER_ENVVAR_PROVIDER_URI


class WorkLockOptions:

    __option_name__ = 'worklock_options'

    def __init__(self,
                 participant_address: ChecksumAddress,
                 signer_uri: str,
                 provider_uri: str,
                 registry_filepath: str,
                 network: str):

        self.bidder_address = participant_address
        self.signer_uri = signer_uri
        self.provider_uri = provider_uri
        self.registry_filepath = registry_filepath
        self.network = network

    def setup(self, general_config) -> tuple:
        emitter = setup_emitter(general_config)   # TODO: Restore Banner:  network=self.network.capitalize()
        registry = get_registry(network=self.network, registry_filepath=self.registry_filepath)
        blockchain = connect_to_blockchain(emitter=emitter, provider_uri=self.provider_uri)
        return emitter, registry, blockchain

    def get_bidder_address(self, emitter, registry):
        if not self.bidder_address:
            self.bidder_address = select_client_account(emitter=emitter,
                                                        provider_uri=self.provider_uri,
                                                        signer_uri=self.signer_uri,
                                                        network=self.network,
                                                        registry=registry,
                                                        show_eth_balance=True)
        return self.bidder_address

    def __create_bidder(self,
                        registry,
                        domain: str,
                        transacting: bool = True,
                        hw_wallet: bool = False,
                        ) -> Bidder:

        is_clef = ClefSigner.is_valid_clef_uri(self.signer_uri)
        testnet = self.network != NetworksInventory.MAINNET
        signer = Signer.from_signer_uri(self.signer_uri, testnet=testnet) if self.signer_uri else None
        password_required = (not is_clef and not hw_wallet)
        if signer and transacting and password_required:
            client_password = get_client_password(checksum_address=self.bidder_address)
            signer.unlock_account(account=self.bidder_address, password=client_password)

        transacting_power = None
        if transacting:
            transacting_power = TransactingPower(account=self.bidder_address, signer=signer)
            transacting_power.unlock(password=client_password)

        bidder = Bidder(registry=registry,
                        transacting_power=transacting_power,
                        checksum_address=self.bidder_address if not transacting_power else None,
                        domain=domain)
        return bidder

    def create_bidder(self, registry, hw_wallet: bool = False):
        return self.__create_bidder(registry=registry,
                                    domain=self.network,
                                    hw_wallet=hw_wallet,
                                    transacting=True)

    def create_transactionless_bidder(self, registry):
        return self.__create_bidder(registry, transacting=False, domain=self.network)


group_worklock_options = group_options(
    WorkLockOptions,
    participant_address=option_participant_address,
    signer_uri=option_signer_uri,
    provider_uri=option_provider_uri(required=True, default=os.environ.get(NUCYPHER_ENVVAR_PROVIDER_URI)),
    network=option_network(default=NetworksInventory.DEFAULT, validate=True),  # TODO: See 2214
    registry_filepath=option_registry_filepath,
)


@click.group()
def worklock():
    """Participate in NuCypher's WorkLock to obtain a NU stake"""


@worklock.command()
@group_worklock_options
@group_general_config
def status(general_config: GroupGeneralConfig, worklock_options: WorkLockOptions):
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
@click.option('--value', help="ETH value to escrow", type=DecimalRange(min=0))
def escrow(general_config: GroupGeneralConfig,
           worklock_options: WorkLockOptions,
           force: bool,
           hw_wallet: bool,
           value: Decimal):
    """Create an ETH escrow, or increase an existing escrow"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    now = maya.now().epoch
    if not worklock_agent.start_bidding_date <= now <= worklock_agent.end_bidding_date:
        emitter.echo(BIDDING_WINDOW_CLOSED, color='red')
        raise click.Abort()

    _bidder_address = worklock_options.get_bidder_address(emitter, registry)
    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    existing_bid_amount = bidder.get_deposited_eth
    if not value:
        if force:
            raise click.MissingParameter("Missing --value.")

        if not existing_bid_amount:  # It's the first bid
            minimum_bid = bidder.worklock_agent.minimum_allowed_bid
            minimum_bid_in_eth = Web3.fromWei(minimum_bid, 'ether')
            prompt = BID_AMOUNT_PROMPT_WITH_MIN_BID.format(minimum_bid_in_eth=minimum_bid_in_eth)
        else:  # There's an existing bid and the bidder is increasing the amount
            emitter.message(EXISTING_BID_AMOUNT_NOTICE.format(eth_amount=Web3.fromWei(existing_bid_amount, 'ether')))
            minimum_bid_in_eth = Web3.fromWei(1, 'ether')
            prompt = BID_INCREASE_AMOUNT_PROMPT
        value = click.prompt(prompt, type=DecimalRange(min=minimum_bid_in_eth))

    value = int(Web3.toWei(Decimal(value), 'ether'))

    if not force:
        if not existing_bid_amount:
            paint_bidding_notice(emitter=emitter, bidder=bidder)
            click.confirm(f"Place WorkLock escrow of {prettify_eth_amount(value)}?", abort=True)
        else:
            click.confirm(f"Increase current escrow ({prettify_eth_amount(existing_bid_amount)}) "
                          f"by {prettify_eth_amount(value)}?", abort=True)

    receipt = bidder.place_bid(value=value)
    emitter.message("Publishing WorkLock Escrow...")

    maximum = NU.from_nunits(bidder.economics.maximum_allowed_locked)
    available_claim = NU.from_nunits(bidder.available_claim)
    message = f'\nCurrent escrow: {prettify_eth_amount(bidder.get_deposited_eth)} | Allocation: {available_claim}\n'
    if available_claim > maximum:
        message += f"\nThis allocation is currently above the allowed max ({maximum}), " \
                   f"so the escrow may be partially refunded.\n"
    message += f'Note that the available allocation value may fluctuate until the escrow period closes and ' \
               f'allocations are finalized.\n'
    emitter.echo(message, color='yellow')

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)


@worklock.command()
@group_general_config
@group_worklock_options
@option_force
@option_hw_wallet
def cancel_escrow(general_config: GroupGeneralConfig, worklock_options: WorkLockOptions, force: bool, hw_wallet: bool):
    """Cancel your escrow and receive your ETH back"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    now = maya.now().epoch
    if not worklock_agent.start_bidding_date <= now <= worklock_agent.end_cancellation_date:
        emitter.echo(CANCELLATION_WINDOW_CLOSED, color='red')
        raise click.Abort()

    bidder_address = worklock_options.get_bidder_address(emitter, registry)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)
    if not force:
        value = bidder.get_deposited_eth
        click.confirm(f"Confirm escrow cancellation of {prettify_eth_amount(value)} for {bidder_address}?", abort=True)
    receipt = bidder.cancel_bid()
    emitter.echo(SUCCESSFUL_BID_CANCELLATION, color='green')
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    return  # Exit


@worklock.command()
@option_force
@option_hw_wallet
@group_worklock_options
@group_general_config
def claim(general_config: GroupGeneralConfig, worklock_options: WorkLockOptions, force: bool, hw_wallet: bool):
    """Claim tokens for your escrow, and start staking them"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    if not worklock_agent.is_claiming_available():
        emitter.echo(CLAIMING_NOT_AVAILABLE, color='red')
        raise click.Abort()

    bidder_address = worklock_options.get_bidder_address(emitter, registry)
    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    unspent_bid = bidder.available_compensation
    if unspent_bid:
        emitter.echo(WORKLOCK_ADDITIONAL_COMPENSATION_AVAILABLE.format(amount=prettify_eth_amount(unspent_bid)))
        if not force:
            message = CONFIRM_REQUEST_WORKLOCK_COMPENSATION.format(bidder_address=bidder_address)
            click.confirm(message, abort=True)
        emitter.echo(REQUESTING_WORKLOCK_COMPENSATION)
        receipt = bidder.withdraw_compensation()
        paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)

    has_claimed = bidder.has_claimed
    if bool(has_claimed):
        emitter.echo(CLAIM_ALREADY_PLACED.format(bidder_address=bidder.checksum_address), color='red')
        raise click.Abort()

    tokens = NU.from_nunits(bidder.available_claim)
    emitter.echo(AVAILABLE_CLAIM_NOTICE.format(tokens=tokens), color='green', bold=True)
    if not force:
        lock_duration = bidder.worklock_agent.worklock_parameters()[-2]
        emitter.echo(WORKLOCK_CLAIM_ADVISORY.format(lock_duration=lock_duration), color='blue')
        click.confirm(CONFIRM_WORKLOCK_CLAIM.format(bidder_address=bidder_address), abort=True)
    emitter.echo(SUBMITTING_WORKLOCK_CLAIM)

    receipt = bidder.claim()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)
    paint_worklock_claim(emitter=emitter,
                         bidder_address=bidder_address,
                         network=worklock_options.network,
                         provider_uri=worklock_options.provider_uri)


@worklock.command()
@group_worklock_options
@group_general_config
def remaining_work(general_config: GroupGeneralConfig, worklock_options: WorkLockOptions):
    """Check how much work is pending until you can get all your escrowed ETH back"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    bidder_address = worklock_options.get_bidder_address(emitter, registry)
    bidder = worklock_options.create_transactionless_bidder(registry=registry)
    emitter.echo(f"Work Remaining for {bidder_address}: {bidder.remaining_work}")


@worklock.command()
@option_force
@option_hw_wallet
@group_worklock_options
@group_general_config
def refund(general_config: GroupGeneralConfig, worklock_options: WorkLockOptions, force: bool, hw_wallet: bool):
    """Reclaim ETH unlocked by your work"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    bidder_address = worklock_options.get_bidder_address(emitter, registry)

    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    if not force:
        click.confirm(CONFIRM_COLLECT_WORKLOCK_REFUND.format(bidder_address=bidder_address), abort=True)
    emitter.echo(SUBMITTING_WORKLOCK_REFUND_REQUEST)

    receipt = bidder.refund_deposit()
    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=bidder.staking_agent.blockchain.client.chain_name)


@worklock.command()
@group_general_config
@group_worklock_options
@option_force
@option_hw_wallet
@click.option('--gas-limit', help="Gas limit per each verification transaction", type=click.IntRange(min=60000))
# TODO: Consider moving to administrator (nucypher-deploy) #1758
def enable_claiming(general_config: GroupGeneralConfig,
                    worklock_options: WorkLockOptions,
                    force: bool,
                    hw_wallet: bool,
                    gas_limit: int):
    """Ensure correctness of WorkLock participants and enable allocation"""
    emitter, registry, blockchain = worklock_options.setup(general_config=general_config)
    bidder_address = worklock_options.get_bidder_address(emitter, registry)
    bidder = worklock_options.create_bidder(registry=registry, hw_wallet=hw_wallet)

    whales = bidder.get_whales()
    if whales:
        headers = ("Participants that require correction", "Current bonus")
        columns = (whales.keys(), map(prettify_eth_amount, whales.values()))
        emitter.echo(tabulate.tabulate(dict(zip(headers, columns)), headers=headers, floatfmt="fancy_grid"))

        if not force:
            click.confirm(f"Confirm force refund to at least {len(whales)} participants using {bidder_address}?", abort=True)

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
                message = CONFIRM_BID_VERIFICATION.format(bidder_address=bidder_address,
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
