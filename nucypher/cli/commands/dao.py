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

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.actors import DaoActor
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.blockchain.eth.signers.software import ClefSigner
from nucypher.cli.actions.auth import get_client_password
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.config import group_general_config, GroupGeneralConfig
from nucypher.cli.options import (
    group_options,
    option_network,
    option_participant_address,
    option_provider_uri,
    option_registry_filepath,
    option_signer_uri,
    option_parameters, option_hw_wallet)
from nucypher.cli.utils import setup_emitter, get_registry, connect_to_blockchain, initialize_deployer_interface
from nucypher.config.constants import NUCYPHER_ENVVAR_PROVIDER_URI

option_parameters.required = True


class DaoOptions:  # TODO: This class is essentially the same that WorkLock options. Generalize and refine.

    __option_name__ = 'dao_options'

    def __init__(self,
                 participant_address: str,
                 signer_uri: str,
                 provider_uri: str,
                 registry_filepath: str,
                 network: str):

        self.participant_address = participant_address
        self.signer_uri = signer_uri
        self.provider_uri = provider_uri
        self.registry_filepath = registry_filepath
        self.network = network

    def setup(self, general_config) -> tuple:
        emitter = setup_emitter(general_config)
        registry = get_registry(network=self.network, registry_filepath=self.registry_filepath)
        blockchain = initialize_deployer_interface(emitter=emitter,
                                                   provider_uri=self.provider_uri,
                                                   poa=False,
                                                   ignore_solidity_check=True)
        return emitter, registry, blockchain

    def get_participant_address(self, emitter, registry, show_staking: bool = False):
        if not self.participant_address:
            self.participant_address = select_client_account(emitter=emitter,
                                                             provider_uri=self.provider_uri,
                                                             signer_uri=self.signer_uri,
                                                             network=self.network,
                                                             registry=registry,
                                                             show_eth_balance=True,
                                                             show_nu_balance=False,
                                                             show_staking=show_staking)
        return self.participant_address

    def __create_participant(self,
                             registry,
                             transacting: bool = True,
                             hw_wallet: bool = False) -> DaoActor:

        client_password = None
        is_clef = ClefSigner.is_valid_clef_uri(self.signer_uri)  # TODO: why not allow the clef signer's validator act on this?
        if transacting and not is_clef and not hw_wallet:
            client_password = get_client_password(checksum_address=self.participant_address)

        testnet = self.network != NetworksInventory.MAINNET
        signer = Signer.from_signer_uri(self.signer_uri, testnet=testnet) if self.signer_uri else None
        actor = DaoActor(checksum_address=self.participant_address,
                         network=self.network,
                         registry=registry,
                         signer=signer,
                         transacting=transacting)
        return actor

    def create_participant(self, registry, hw_wallet: bool = False):
        return self.__create_participant(registry=registry, hw_wallet=hw_wallet, transacting=True)

    def create_transactionless_participant(self, registry):
        return self.__create_participant(registry, transacting=False)


group_dao_options = group_options(
    DaoOptions,
    participant_address=option_participant_address,
    signer_uri=option_signer_uri,
    provider_uri=option_provider_uri(required=True, default=os.environ.get(NUCYPHER_ENVVAR_PROVIDER_URI)),
    network=option_network(required=True),
    registry_filepath=option_registry_filepath,
)


@click.group()
def dao():
    """Participate in the NuCypher DAO"""


@dao.command()
@group_general_config
def inspect(general_config: GroupGeneralConfig):
    """Show current status of the NuCypher DAO"""


@dao.command()
@group_general_config
@group_dao_options
@option_hw_wallet
@option_parameters
def propose(general_config: GroupGeneralConfig, dao_options: DaoOptions, hw_wallet, parameters):
    """Make a proposal for the NuCypher DAO"""
    # TODO: Find a good way to produce different proposals, such as:
    #  - Upgrade contract (in particular, retarget to a deployed one)
    #  - Activate network
    #  - Transfer ownership of contract
    #  - Change global fee range in PolicyManager
    #  - Change composition of Emergency Response Team
    #  - Change Standard/Emergency voting settings (% approval, % support)

    emitter, registry, blockchain = dao_options.setup(general_config=general_config)
    _participant_address = dao_options.get_participant_address(emitter, registry, show_staking=True)

    manager = dao_options.create_participant(registry=registry, hw_wallet=hw_wallet)
    with open(parameters) as json_file:
        parameters = json.load(json_file)

    manager.period_extension_proposal(**parameters)


@dao.command()
@group_general_config
def validate(general_config: GroupGeneralConfig):
    """Validate an existing proposal"""
