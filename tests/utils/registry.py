import json
from pathlib import Path
from typing import Dict

from eth_utils import to_checksum_address

from nucypher.blockchain.eth.registry import InMemoryContractRegistry


def registry_from_ape_deployments(build_path: Path, deployments: Dict) -> InMemoryContractRegistry:
    """Creates a registry from ape deployments."""

    def get_json_abi(path):
        with open(path, 'r') as f:
            _abi = json.load(f)['abi']
        return _abi

    data = list()
    for contract_name, deployment in deployments.items():
        path = build_path / f"{contract_name}.json"
        abi = get_json_abi(path)
        entry = [
            contract_name,
            'v0.0.0',  # TODO: get version from contract
            to_checksum_address(deployment.address),
            abi
        ]
        data.append(entry)
    registry = InMemoryContractRegistry()
    registry.write(data)
    return registry
