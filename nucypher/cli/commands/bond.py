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

from typing import Tuple, Union

import click
import maya
from eth_typing import ChecksumAddress

from nucypher.blockchain.eth.agents import ContractAgency, PREApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.signers import Signer
from nucypher.cli.actions.auth import get_client_password
from nucypher.cli.actions.select import select_network
from nucypher.cli.literature import (
    STAKING_PROVIDER_UNAUTHORIZED,
    BONDING_TIME,
    ALREADY_BONDED,
    UNEXPECTED_HUMAN_OPERATOR,
    BONDING,
    CONFIRM_BONDING,
    NOT_BONDED,
    CONFIRM_UNBONDING,
    UNBONDING
)
from nucypher.cli.options import (
    option_registry_filepath,
    option_signer_uri,
    option_eth_provider_uri,
    option_network,
    option_staking_provider,
    option_operator_address,
    option_force
)
from nucypher.cli.painting.transactions import paint_receipt_summary
from nucypher.cli.utils import connect_to_blockchain, get_registry
from nucypher.config.constants import NUCYPHER_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD
from nucypher.control.emitters import StdoutEmitter
from nucypher.crypto.powers import TransactingPower


def is_authorized(emitter, staking_provider: ChecksumAddress, agent: PREApplicationAgent) -> None:
    _authorized = agent.is_authorized(staking_provider=staking_provider)
    if not _authorized:
        emitter.message(STAKING_PROVIDER_UNAUTHORIZED.format(provider=staking_provider), color='red')
        raise click.Abort()


def is_bonded(agent, staking_provider: ChecksumAddress, return_address: bool = False) -> Union[bool, Tuple[bool, ChecksumAddress]]:
    onchain_operator = agent.get_operator_from_staking_provider(staking_provider=staking_provider)
    result = onchain_operator != NULL_ADDRESS
    if not return_address:
        return result
    return result, onchain_operator


def check_bonding_requirements(emitter, agent: PREApplicationAgent, staking_provider: ChecksumAddress) -> None:
    blockchain = agent.blockchain
    now = blockchain.get_blocktime()
    commencement = agent.get_staking_provider_info(staking_provider=staking_provider).operator_start_timestamp
    min_seconds = agent.get_min_operator_seconds()
    termination = (commencement + min_seconds)
    if now < termination:
        emitter.error(BONDING_TIME.format(date=maya.MayaDT(termination)))
        raise click.Abort()


@click.command('bond')
@option_registry_filepath
@option_eth_provider_uri(required=True)
@option_signer_uri
@option_operator_address
@option_staking_provider
@option_network(required=True)
@option_force
def bond(registry_filepath, eth_provider_uri, signer_uri, operator_address, staking_provider, network, force):
    """
    Bond an operator to a staking provider.
    The staking provider must be authorized to use the PREApplication.
    """

    #
    # Setup
    #

    emitter = StdoutEmitter()
    connect_to_blockchain(eth_provider_uri=eth_provider_uri, emitter=emitter)
    if not signer_uri:
        emitter.message('--signer is required', color='red')
        raise click.Abort()
    if not network:
        network = select_network(emitter=emitter, network_type=NetworksInventory.ETH)

    signer = Signer.from_signer_uri(signer_uri)
    transacting_power = TransactingPower(account=staking_provider, signer=signer)
    registry = get_registry(network=network, registry_filepath=registry_filepath)
    agent = ContractAgency.get_agent(PREApplicationAgent, registry=registry)

    #
    # Checks
    #

    # Check for authorization
    is_authorized(emitter=emitter, agent=agent, staking_provider=staking_provider)

    # Check bonding
    if is_bonded(agent=agent, staking_provider=staking_provider, return_address=False):
        # operator is already set - check timing
        check_bonding_requirements(emitter=emitter, agent=agent, staking_provider=staking_provider)

    # Check for pre-existing staking providers for this operator
    onchain_staking_provider = agent.get_staking_provider_from_operator(operator_address=operator_address)
    if onchain_staking_provider != NULL_ADDRESS:
        emitter.message(ALREADY_BONDED.format(provider=onchain_staking_provider, operator=operator_address), color='red')
        raise click.Abort()  # dont steal bananas

    # Check that operator is not human
    if staking_provider != operator_address:
        # if the operator has a beneficiary it is the staking provider.
        beneficiary = agent.get_beneficiary(staking_provider=operator_address)
        if beneficiary != NULL_ADDRESS:
            emitter.message(UNEXPECTED_HUMAN_OPERATOR, color='red')
            raise click.Abort()

    #
    # Bond
    #

    if not force:
        click.confirm(CONFIRM_BONDING.format(provider=staking_provider, operator=operator_address), abort=True)
    transacting_power.unlock(password=get_client_password(checksum_address=staking_provider, envvar=NUCYPHER_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD))
    emitter.echo(BONDING.format(operator=operator_address))
    receipt = agent.bond_operator(operator=operator_address, transacting_power=transacting_power, staking_provider=staking_provider)
    paint_receipt_summary(receipt=receipt, emitter=emitter)


@click.command('unbond')
@option_registry_filepath
@option_eth_provider_uri(required=True)
@option_signer_uri
@option_staking_provider
@option_network()
@option_force
def unbond(registry_filepath, eth_provider_uri, signer_uri, staking_provider, network, force):
    """Unbonds an operator from an authorized staking provider."""

    #
    # Setup
    #
    
    emitter = StdoutEmitter()
    if not signer_uri:
        emitter.message('--signer is required', color='red')
        raise click.Abort()
    if not network:
        network = select_network(emitter=emitter, network_type=NetworksInventory.ETH)

    connect_to_blockchain(eth_provider_uri=eth_provider_uri, emitter=emitter)
    registry = get_registry(network=network, registry_filepath=registry_filepath)
    agent = ContractAgency.get_agent(PREApplicationAgent, registry=registry)
    signer = Signer.from_signer_uri(signer_uri)
    transacting_power = TransactingPower(account=staking_provider, signer=signer)

    #
    # Check
    #
    
    bonded, onchain_operator_address = is_bonded(agent=agent, staking_provider=staking_provider, return_address=True)
    if not bonded:
        emitter.message(NOT_BONDED.format(provider=staking_provider), color='red')
        raise click.Abort()
    check_bonding_requirements(emitter=emitter, agent=agent, staking_provider=staking_provider)

    #
    # Unbond
    #

    if not force:
        click.confirm(CONFIRM_UNBONDING.format(provider=staking_provider, operator=onchain_operator_address), abort=True)
    transacting_power.unlock(password=get_client_password(checksum_address=staking_provider, envvar=NUCYPHER_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD))
    emitter.echo(UNBONDING.format(operator=onchain_operator_address))
    receipt = agent.bond_operator(operator=NULL_ADDRESS, transacting_power=transacting_power, staking_provider=staking_provider)
    paint_receipt_summary(receipt=receipt, emitter=emitter)
