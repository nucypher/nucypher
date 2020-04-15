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

import json
import os

import click

from nucypher.blockchain.eth.actors import Trustee, Executive
from nucypher.blockchain.eth.agents import NucypherTokenAgent, ContractAgency, MultiSigAgent
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.multisig import Proposal, Authorization
from nucypher.blockchain.eth.registry import LocalContractRegistry, InMemoryContractRegistry
from nucypher.blockchain.eth.signers import ClefSigner
from nucypher.cli.actions import (
    get_client_password,
    select_client_account,
    get_provider_process)
from nucypher.cli.commands.stake import option_signer_uri
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_checksum_address,
    option_config_root,
    option_etherscan,
    option_force,
    option_hw_wallet,
    option_light,

    option_network,
    option_poa,
    option_provider_uri,

    option_registry_filepath, option_geth)
from nucypher.cli.painting import (
    paint_receipt_summary,
    paint_multisig_contract_info,
    paint_multisig_proposed_transaction
)
from nucypher.cli.types import EXISTING_READABLE_FILE
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


def _setup_emitter(general_config):
    emitter = general_config.emitter
    return emitter


def _initialize_blockchain(poa, provider_uri, emitter, gas_strategy=None):
    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        # Note: For test compatibility.
        deployer_interface = BlockchainDeployerInterface(provider_uri=provider_uri,
                                                         poa=poa,
                                                         gas_strategy=gas_strategy)

        BlockchainInterfaceFactory.register_interface(interface=deployer_interface,
                                                      sync=False,
                                                      emitter=emitter)
    else:
        deployer_interface = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)

    deployer_interface.connect()
    return deployer_interface


def _ensure_config_root(config_root):
    # Ensure config root exists, because we need a default place to put output files.
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)


# TODO: Same option group in nucypher status (called RegistryOptions). Make something generic
class BlockchainOptions:

    __option_name__ = 'blockchain_options'

    def __init__(self, provider_uri, geth, poa, registry_filepath, light, network):
        self.provider_uri = provider_uri
        self.geth = geth
        self.poa = poa
        self.registry_filepath = registry_filepath
        self.light = light
        self.network = network

    def get_registry(self, connect_blockchain: bool = False, emitter=None, debug=None):
        if connect_blockchain:
            self.connect_blockchain(emitter, debug)
        if self.registry_filepath:
            registry = LocalContractRegistry(filepath=self.registry_filepath)
        else:
            registry = InMemoryContractRegistry.from_latest_publication(network=self.network)
        return registry

    def connect_blockchain(self, emitter, debug):
        try:
            eth_node = None
            if self.geth:
                eth_node = get_provider_process()

            # Note: For test compatibility.
            if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=self.provider_uri):
                BlockchainInterfaceFactory.initialize_interface(provider_uri=self.provider_uri,
                                                                provider_process=eth_node,
                                                                poa=self.poa,
                                                                light=self.light,
                                                                sync=False,
                                                                emitter=emitter)

            blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=self.provider_uri)

            emitter.echo(message="Reading Latest Chaindata...")
            blockchain.connect()
            return blockchain
        except Exception as e:
            if debug:
                raise
            click.secho(str(e), bold=True, fg='red')
            raise click.Abort


group_blockchain_options = group_options(
    BlockchainOptions,
    provider_uri=option_provider_uri(),
    geth=option_geth,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network,
)


class MultiSigOptions:
    __option_name__ = 'multisig_options'

    def __init__(self, checksum_address, signer_uri, hw_wallet):
        self.checksum_address = checksum_address
        self.signer_uri = signer_uri
        self.hw_wallet = hw_wallet

    def __create_executive(self, registry, transacting: bool = False) -> Executive:
        client_password = None
        if transacting and not self.hw_wallet:
            client_password = get_client_password(checksum_address=self.checksum_address)
        executive = Executive(checksum_address=self.checksum_address,
                              registry=registry,
                              signer=ClefSigner(self.signer_uri),
                              client_password=client_password)
        return executive

    def create_executive(self, registry) -> Executive:  # TODO: Reconsider this method: Executives don't transact, just sign.
        return self.__create_executive(registry, transacting=True)

    def create_transactingless_executive(self, registry) -> Executive:
        return self.__create_executive(registry, transacting=False)

    def __create_trustee(self, registry, transacting: bool = False) -> Trustee:
        client_password = None
        if transacting and not self.hw_wallet:
            client_password = get_client_password(checksum_address=self.checksum_address)
        trustee = Trustee(checksum_address=self.checksum_address, registry=registry, client_password=client_password)
        return trustee

    def create_trustee(self, registry) -> Trustee:
        return self.__create_trustee(registry, transacting=True)

    def create_transactingless_trustee(self, registry) -> Trustee:
        return self.__create_trustee(registry, transacting=False)


group_multisig_options = group_options(
    MultiSigOptions,
    checksum_address=option_checksum_address,
    signer_uri=option_signer_uri,
    hw_wallet=option_hw_wallet
)


@click.group()
def multisig():
    """
    Perform operations on NuCypher contracts via a MultiSig
    """
    pass


@multisig.command()
@group_general_config
@group_blockchain_options
def inspect(general_config, blockchain_options):
    """
    Show information of the MultiSig contract
    """
    # Init
    emitter = general_config.emitter
    _blockchain = blockchain_options.connect_blockchain(emitter, general_config.debug)
    registry = blockchain_options.get_registry()

    multisig_agent = ContractAgency.get_agent(MultiSigAgent, registry=registry)
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)

    paint_multisig_contract_info(emitter, multisig_agent, token_agent)
    return


@multisig.command()
@group_general_config
@group_blockchain_options
@group_multisig_options
def propose(general_config, blockchain_options, multisig_options):
    """
    Create a proposal of MultiSig transaction
    """
    # TODO: Extend this command to cover this list of proposals
    #  - Add new MultiSig owner
    #  - Remove MultiSig owner
    #  - Change threshold of MultiSig
    #  - Upgrade contract (in particular, retarget to a deployed one)
    #  - Transfer ownership of contract
    #  - Send ETH from MultiSig
    #  - Send tokens from MultiSig
    #  - Change min reward rate range in PolicyManager
    #  - Send raw transaction

    # Init
    emitter = general_config.emitter
    #_ensure_config_root(actor_options.config_root)
    blockchain = blockchain_options.connect_blockchain(emitter, general_config.debug)
    registry = blockchain_options.get_registry()

    if not multisig_options.checksum_address:
        multisig_options.checksum_address = select_client_account(emitter=emitter,
                                                                  provider_uri=blockchain_options.provider_uri,
                                                                  poa=blockchain_options.poa,
                                                                  network=blockchain_options.network,
                                                                  registry=registry,
                                                                  show_balances=True)

    trustee = multisig_options.create_transactingless_trustee(registry)

    # As a PoC, this command only allows to change the threshold
    # TODO: Think in the UX for choosing between different types of proposals

    new_threshold = click.prompt("New threshold", type=click.INT)
    proposal = trustee.propose_changing_threshold(new_threshold)

    paint_multisig_proposed_transaction(emitter=emitter, proposal=proposal, registry=registry)

    filepath = f'proposal-changeThreshold-{trustee.multisig_agent.contract_address[:8]}-TX-{proposal.nonce}.json'
    proposal.write(filepath=filepath)
    emitter.echo(f"✅ Saved proposal to {filepath}", color='blue', bold=True)


@multisig.command()
@group_general_config
@group_blockchain_options
@group_multisig_options
@click.option('--proposal', help="Filepath to a JSON file containing a multisig transaction data",
              type=EXISTING_READABLE_FILE, required=True)
def sign(general_config, blockchain_options, multisig_options, proposal):
    """
    Sign a proposed transaction before being sent to the MultiSig contract for execution
    """
    # Init
    emitter = general_config.emitter
    #_ensure_config_root(actor_options.config_root)
    blockchain = blockchain_options.connect_blockchain(emitter, general_config.debug)
    registry = blockchain_options.get_registry()

    proposal = Proposal.from_file(proposal)

    if not multisig_options.checksum_address:
        multisig_options.checksum_address = select_client_account(emitter=emitter,
                                                                  provider_uri=blockchain_options.provider_uri,
                                                                  poa=blockchain_options.poa,
                                                                  network=blockchain_options.network,
                                                                  registry=registry,
                                                                  show_balances=True)

    name, version, address, abi = registry.search(contract_address=proposal.target_address)
    # TODO: This assumes that we're always signing proxy retargetting. For the moment is true.
    proxy_contract = blockchain.client.w3.eth.contract(abi=abi,
                                                       address=address,
                                                       version=version,
                                                       ContractFactoryClass=blockchain._contract_factory)
    paint_multisig_proposed_transaction(emitter, proposal, proxy_contract)

    click.confirm("Proceed with signing?", abort=True)

    executive = multisig_options.create_transactingless_executive(registry)  # FIXME: Since we use a signer, don't ask for PW
    authorization = executive.authorize_proposal(proposal)
    emitter.echo(f"\nSignature received from {authorization.recover_executive_address(proposal)}:\n")
    emitter.echo(f"{authorization.serialize().hex()}\n", bold=True, color='green')


@multisig.command()
@group_general_config
@group_blockchain_options
@group_multisig_options
@click.option('--proposal', help="Filepath to a JSON file containing a multisig transaction data",
              type=EXISTING_READABLE_FILE, required=True)
def execute(general_config, blockchain_options, multisig_options, proposal):
    """
    Collect authorizations from executives and execute transaction through MultiSig contract
    """
    # Init
    emitter = general_config.emitter
    #_ensure_config_root(actor_options.config_root)
    blockchain = blockchain_options.connect_blockchain(emitter, general_config.debug)
    registry = blockchain_options.get_registry()

    proposal = Proposal.from_file(proposal)

    if not multisig_options.checksum_address:
        multisig_options.checksum_address = select_client_account(emitter=emitter,
                                                                  provider_uri=blockchain_options.provider_uri,
                                                                  poa=blockchain_options.poa,
                                                                  network=blockchain_options.network,
                                                                  registry=registry,
                                                                  show_balances=True)

    name, version, address, abi = registry.search(contract_address=proposal.target_address)
    # TODO: This assumes that we're always signing proxy retargetting. For the moment is true.
    proxy_contract = blockchain.client.w3.eth.contract(abi=abi,
                                                       address=address,
                                                       version=version,
                                                       ContractFactoryClass=blockchain._contract_factory)
    paint_multisig_proposed_transaction(emitter, proposal, proxy_contract)

    trustee = multisig_options.create_trustee(registry)
    threshold = trustee.multisig_agent.threshold

    while len(trustee.authorizations) < threshold:
        auth_hex = click.prompt("Signature", type=click.STRING)
        authorization = Authorization.from_hex(auth_hex)
        executive_address = trustee.add_authorization(authorization, proposal)
        emitter.echo(f"Added authorization from executive {executive_address}", color='green')

    click.confirm("\nCollected required authorizations. Proceed with execution?", abort=True)

    receipt = trustee.execute(proposal)
    paint_receipt_summary(emitter, receipt)
