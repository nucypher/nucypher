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
from collections import namedtuple
from typing import Iterable, Tuple, Union, List, Dict, NamedTuple

from eth_typing import ChecksumAddress, HexStr
from eth_utils import to_canonical_address
from web3 import Web3
from web3.contract import ContractFunction

from nucypher.blockchain.eth import BASE_DIRECTORY, CONTRACT_REGISTRY_BASE
from nucypher.blockchain.eth.constants import DAO_INSTANCES_NAMES
from nucypher.blockchain.eth.networks import NetworksInventory


class Action(NamedTuple):
    """
    An action is the conjunction of a smart contract address and a call to one of its methods
    """
    target: ChecksumAddress
    data: Union[ContractFunction, HexStr, bytes]


class CallScriptCodec:
    """
    Utility class to facilitate encoding 'actions' (i.e, calls to smart contracts)
    as per the CallScript format used by Aragon contracts.
    """

    CALLSCRIPT_ID = Web3.toBytes(hexstr='0x00000001')

    @classmethod
    def encode_actions(cls, actions: Iterable[Action]) -> bytes:
        callscript = [cls.CALLSCRIPT_ID]

        actions = cls._format_actions(actions=actions)
        for target, action_data in actions:
            encoded_action = (to_canonical_address(target),
                              len(action_data).to_bytes(4, 'big'),
                              action_data)
            callscript.extend(encoded_action)

        callscript_data = b''.join(callscript)
        return callscript_data

    @classmethod
    def _format_actions(cls, actions: Iterable[Action]) -> Iterable[Tuple[ChecksumAddress, bytes]]:
        actions_bytes = list()
        for target, function_call in actions:
            try:
                encoded_action = function_call._encode_transaction_data()
            except AttributeError:
                encoded_action = function_call

            try:
                action_bytes = Web3.toBytes(hexstr=encoded_action)
            except TypeError:
                action_bytes = encoded_action

            actions_bytes.append((target, action_bytes))

        return actions_bytes


class Artifact:
    """
    A helper class to extract data from Aragon's Artifacts, which contain metadata about Aragon's apps.
    """
    ARTIFACTS_DIRECTORY = BASE_DIRECTORY / "aragon_artifacts"

    def __init__(self, name: str):
        artifact_filepath = self.ARTIFACTS_DIRECTORY / f"{name}.json"
        with open(artifact_filepath, 'r') as artifact_file:
            self.raw_data = json.load(artifact_file)

    @property
    def abi(self) -> List[Dict]:
        return self.raw_data["abi"]


class DAORegistry:
    """
    A simple registry to store the addresses and types of NuCypher DAO instances.
    An instance is a particular specimen of an Aragon App.
    An Aragon App may have several instances in the NuCypher DAO (e.g., there are two instances of the Voting app)
    """

    _REGISTRY_FILENAME = "dao_registry.json"

    Instance = namedtuple('Instance', ['name', 'app_name', 'address'])

    class InstanceNotInRegistry(RuntimeError):
        """Raised when a instance is not found in the NuCypher DAO registry"""

    def __init__(self, network: str):
        self.network = network
        self.filepath = self.get_filepath(network)
        with open(self.filepath, 'r') as registry_file:
            raw_dao_elements = dict(json.load(registry_file))

        self.instances = dict()
        for instance_name, instance_data in raw_dao_elements.items():
            self.__validate_instance_name(instance_name)
            self.instances[instance_name] = self.Instance(name=instance_name, **instance_data)

    @classmethod
    def get_filepath(cls, network: str):
        NetworksInventory.validate_network_name(network)
        filepath = CONTRACT_REGISTRY_BASE / network / cls._REGISTRY_FILENAME
        return filepath

    @staticmethod
    def __validate_instance_name(instance_name: str):
        if instance_name not in DAO_INSTANCES_NAMES:
            raise ValueError(f"{instance_name} is not a recognized instance of NuCypherDAO.")

    def get_instance(self, instance_name: str):
        self.__validate_instance_name(instance_name)
        try:
            instance = self.instances[instance_name]
        except KeyError:
            raise self.InstanceNotInRegistry(f"{instance_name} is not found in the NuCypherDAO registry.")
        else:
            return instance

    def get_address_of(self, instance_name: str) -> ChecksumAddress:
        instance = self.get_instance(instance_name)
        return ChecksumAddress(instance.address)

    def get_app_name_of(self, instance_name: str) -> str:
        instance = self.get_instance(instance_name)
        return instance.app_name

    def get_instance_name_by_address(self, address: ChecksumAddress) -> str:
        for instance_name, instance in self.instances.items():
            if instance.address == address:
                return instance_name
        else:
            raise self.InstanceNotInRegistry(f"No instance found in the NuCypherDAO registry with address {address}")
