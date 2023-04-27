import json
from eth_utils import to_checksum_address
from pathlib import Path

from ape.api import DependencyAPI
from copy import deepcopy

from typing import Dict, Any
from ape import config as ape_config

from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    PREApplicationAgent,
    SubscriptionManagerAgent,
    CoordinatorAgent
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from tests.constants import MOCK_STAKING_CONTRACT_NAME


# order sensitive
_CONTRACTS_TO_DEPLOY_ON_TESTERCHAIN = (
    NucypherTokenAgent.contract_name,
    MOCK_STAKING_CONTRACT_NAME,
    PREApplicationAgent.contract_name,
    SubscriptionManagerAgent.contract_name,
    CoordinatorAgent.contract_name,
)


def get_ape_project_build_path(project) -> Path:
    build_path = Path(project.path) / '.build'
    return build_path


def process_deployment_params(contract_name, params, deployments) -> Dict[str, Any]:
    """
    Process deployment params for a contract.
    """
    processed_params = dict()
    for k, v in params.items():
        if isinstance(v, str) and (v.startswith("::") and v.endswith("::")):
            try:
                dependency_name = v.strip("::")
                v = deployments[dependency_name].address
            except KeyError:
                raise ValueError(f"Contract {contract_name} not found in deployments")
        processed_params[k] = v
    return processed_params


def get_deployment_params(contract_name, config, deployments) -> dict:
    """
    Get deployment params for a contract.
    """
    config = deepcopy(config)
    while config:
        params = config.pop()
        name = params.pop("contract_type")
        if name == contract_name:
            params = process_deployment_params(contract_name, params, deployments)
            return params
    else:
        # there are no deployment params for this contract
        return dict()


def deploy_contracts(nucypher_contracts: DependencyAPI, accounts, deployer_account_index: int = 0):
    """Deploy contracts o via ape's API for testing."""
    config = ape_config.get_config("deployments")["ethereum"]["local"]
    deployer_account = accounts[deployer_account_index]
    deployments = dict()
    for name in _CONTRACTS_TO_DEPLOY_ON_TESTERCHAIN:
        params = get_deployment_params(name, deployments=deployments, config=config)
        dependency_contract = getattr(nucypher_contracts, name)
        deployed_contract = deployer_account.deploy(dependency_contract, *params.values())
        deployments[name] = deployed_contract
    return deployments


def registry_from_ape_deployments(project, deployments: Dict) -> InMemoryContractRegistry:
    """Creates a registry from ape deployments."""

    build_path = get_ape_project_build_path(project)

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
