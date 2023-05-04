import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Tuple

from ape import config as ape_config
from ape.api import DependencyAPI
from eth_typing import ChecksumAddress
from eth_utils import is_checksum_address, to_checksum_address

from nucypher.blockchain.eth.agents import (
    CoordinatorAgent,
    NucypherTokenAgent,
    PREApplicationAgent,
    SubscriptionManagerAgent,
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


def process_deployment_params(
    contract_name, params, deployments, symbol: str = "::"
) -> Dict[str, Any]:
    """Process deployment params for a contract."""
    processed_params = dict()
    for k, v in params.items():
        if isinstance(v, str) and (v.startswith(symbol) and v.endswith(symbol)):
            dependency_expression = v.strip(symbol)
            dependency_name, attribute_name = dependency_expression.split(".")
            try:
                v = getattr(deployments[dependency_name], attribute_name)
            except KeyError:
                raise ValueError(f"Contract {contract_name} not found in deployments")
            except AttributeError:
                raise ValueError(
                    f"Attribute {attribute_name} not found in {dependency_name}"
                )
        processed_params[k] = v
    return processed_params


def get_deployment_params(
    contract_name, config, accounts, deployments
) -> Tuple[Dict, ChecksumAddress]:
    """
    Get deployment params for a contract.
    """
    config = deepcopy(config)
    while config:
        params = config.pop()
        deployer_address = params.pop("address")
        name = params.pop("contract_type")
        if not is_checksum_address(deployer_address):
            try:
                deployer_address = ChecksumAddress(accounts[int(deployer_address)])
            except IndexError:
                raise ValueError(f"Invalid deployer account index {deployer_address}")
            except ValueError:
                raise ValueError(
                    f"Invalid configuration value for {name}'s deployment account: {deployer_address}"
                )
        if name == contract_name:
            params = process_deployment_params(contract_name, params, deployments)
            return params, deployer_address
    else:
        # there are no deployment params for this contract
        return dict(), ChecksumAddress(deployer_address)


def deploy_contracts(nucypher_contracts: DependencyAPI, accounts):
    """Deploy contracts o via ape's API for testing."""
    config = ape_config.get_config("deployments")["ethereum"]["local"]
    deployments = dict()
    for name in _CONTRACTS_TO_DEPLOY_ON_TESTERCHAIN:
        params, deployer_account = get_deployment_params(
            name, deployments=deployments, config=config, accounts=accounts
        )
        dependency_contract = getattr(nucypher_contracts, name)
        deployed_contract = deployer_account.deploy(dependency_contract, *params.values())
        deployments[name] = deployed_contract
    return deployments


def registry_from_ape_deployments(nucypher_contracts: DependencyAPI, deployments: Dict) -> InMemoryContractRegistry:
    """Creates a registry from ape deployments."""

    # Get the raw abi from the cached manifest
    manifest = json.loads(nucypher_contracts.cached_manifest.json())
    contract_data = manifest['contractTypes']

    data = list()
    for contract_name, deployment in deployments.items():
        abi = contract_data[contract_name]['abi']
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
