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

from nucypher.blockchain.eth.actors import ContractAdministrator, Trustee, Executive
from nucypher.blockchain.eth.agents import NucypherTokenAgent, ContractAgency, MultiSigAgent
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import LocalContractRegistry, InMemoryContractRegistry
from nucypher.cli.actions import (
    get_client_password,
    select_client_account,
    establish_deployer_registry,
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
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE
from nucypher.cli.types import WEI
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

    def __init__(self, checksum_address, signer_uri):
        self.checksum_address = checksum_address
        self.signer_uri = signer_uri

    def __create_executive(self, registry, transacting: bool = False, hw_wallet: bool = False):
        client_password = None
        if transacting and not hw_wallet:
            client_password = get_client_password(checksum_address=self.checksum_address)
        executive = Executive(checksum_address=self.checksum_address,
                              registry=registry,
                              client_password=client_password,
                              is_transacting=transacting)
        return executive

    def create_executive(self, registry, hw_wallet: bool = False):
        return self.__create_executive(registry, transacting=True, hw_wallet=hw_wallet)

    def create_transactionless_executive(self, registry):
        return self.__create_executive(registry, transacting=False)


group_multisig_options = group_options(
    MultiSigOptions,
    checksum_address=option_checksum_address,
    signer_uri=option_signer_uri
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
@click.option('--proposal', help="Filepath to a JSON file containing a multisig transaction data",
              type=EXISTING_READABLE_FILE)
def sign(general_config, blockchain_options, multisig_options, proposal):
    """
    Sign a proposed transaction before being sent to the MultiSig contract for execution
    """
    # Init
    emitter = general_config.emitter
    #_ensure_config_root(actor_options.config_root)
    blockchain = blockchain_options.connect_blockchain(emitter, general_config.debug)
    registry = blockchain_options.get_registry()

    if not proposal:
        raise click.MissingParameter("nucypher multisig sign requires the use of --proposal")

    with open(proposal) as json_file:
        proposal = json.load(json_file)

    executive_summary = proposal['parameters']

    name, version, address, abi = registry.search(contract_address=executive_summary['target_address'])
    # TODO: This assumes that we're always signing proxy retargetting. For the moment is true.
    proxy_contract = blockchain.client.w3.eth.contract(abi=abi,
                                                       address=address,
                                                       version=version,
                                                       ContractFactoryClass=blockchain._contract_factory)
    paint_multisig_proposed_transaction(emitter, proposal, proxy_contract)

    click.confirm("Proceed with signing?", abort=True)

    # TODO: Blocked by lack of support to EIP191 - #1566
