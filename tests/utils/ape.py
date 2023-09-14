from typing import List

from ape.contracts.base import ContractInstance
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.registry import InMemoryContractRegistry


def registry_from_ape_deployments(
    deployments: List[ContractInstance],
) -> InMemoryContractRegistry:
    """Creates a registry from ape deployments."""
    data = list()

    for contract_instance in deployments:
        abi_json_list = []
        for entry in contract_instance.contract_type.abi:
            abi_json_list.append(entry.dict())

        entry = [
            contract_instance.contract_type.name,
            'v0.0.0',  # TODO: get version from contract
            to_checksum_address(contract_instance.address),
            abi_json_list,
        ]
        data.append(entry)
    registry = InMemoryContractRegistry()
    registry.write(data)
    return registry
