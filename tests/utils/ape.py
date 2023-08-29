import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Tuple, Union

from ape import config as ape_config
from ape import project
from ape.api import DependencyAPI
from ape.contracts.base import ContractInstance
from ape_test.accounts import TestAccount
from eth_typing import ChecksumAddress
from eth_utils import is_checksum_address, to_checksum_address

from nucypher.blockchain.eth.agents import (
    CoordinatorAgent,
    NucypherTokenAgent,
    PREApplicationAgent,
    SubscriptionManagerAgent,
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from tests.constants import (
    CONDITION_NFT,
    MOCK_STAKING_CONTRACT_NAME,
    RITUAL_TOKEN,
    STAKE_INFO,
    T_TOKEN,
)

# order sensitive
_CONTRACTS_TO_DEPLOY_ON_TESTERCHAIN = (
    RITUAL_TOKEN,
    T_TOKEN,
    NucypherTokenAgent.contract_name,
    STAKE_INFO,
    MOCK_STAKING_CONTRACT_NAME,
    PREApplicationAgent.contract_name,
    SubscriptionManagerAgent.contract_name,
    CoordinatorAgent.contract_name,
    CONDITION_NFT,
)

VARIABLE_PREFIX_SYMBOL = "<"
VARIABLE_SUFIX_SYMBOL = ">"

def get_ape_project_build_path(project) -> Path:
    build_path = Path(project.path) / '.build'
    return build_path


def _is_variable(param: Union[str, int, List[Union[str, int]]]) -> bool:
    """Check if param is a ape-config variable"""
    return isinstance(param, str) and (
        param.startswith(VARIABLE_PREFIX_SYMBOL)
        and param.endswith(VARIABLE_SUFIX_SYMBOL)
    )


def _resolve_variable(
    param: str,
    contract_name: str,
    deployments: Dict[str, ContractInstance],
    accounts: List[TestAccount],
) -> Union[ChecksumAddress, str, int]:
    """Resolve a ape-config variable to a literal"""
    dependency_expression = param.strip(VARIABLE_PREFIX_SYMBOL).strip(
        VARIABLE_SUFIX_SYMBOL
    )
    dependency_name, attribute_name = dependency_expression.split(".")
    if dependency_name == "address":
        try:
            account = accounts[int(attribute_name)]
        except ValueError:
            raise ValueError(
                f"Ape account must be accessed by an index; got '{attribute_name}'."
            )
        address = ChecksumAddress(account.address)
        return address
    try:
        param = getattr(deployments[dependency_name], attribute_name)
    except KeyError:
        raise ValueError(f"Contract {contract_name} not found in deployments")
    except AttributeError:
        raise ValueError(f"Attribute {attribute_name} not found in {dependency_name}")
    return param


def process_deployment_params(
    contract_name: str,
    params: Dict[str, Union[str, int, list]],
    deployments: Dict[str, ContractInstance],
    accounts: List[TestAccount],
) -> Dict[str, Union[ChecksumAddress, str, int]]:
    """Process deployment params for a contract."""
    processed_params = dict()
    for param_name, param_value in params.items():
        if _is_variable(param_value):
            param_value = _resolve_variable(
                param=param_value,
                contract_name=contract_name,
                deployments=deployments,
                accounts=accounts,
            )
            processed_params[param_name] = param_value
            continue

        elif isinstance(param_value, list):
            value_list = list()
            for param in param_value:
                if _is_variable(param):
                    param = _resolve_variable(
                        param=param,
                        contract_name=contract_name,
                        deployments=deployments,
                        accounts=accounts,
                    )

                value_list.append(param)

            processed_params[param_name] = value_list
            continue

        else:
            # this parameter is a literal
            processed_params[param_name] = param_value
            continue

    return processed_params


def get_deployment_params(
    contract_name: str,
    config: Dict[str, Union[str, list]],
    accounts: List[TestAccount],
    deployments: Dict[str, ContractInstance],
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
            params = process_deployment_params(
                contract_name=contract_name,
                params=params,
                deployments=deployments,
                accounts=accounts,
            )
            return params, deployer_address
    else:
        # there are no deployment params for this contract
        return dict(), ChecksumAddress(deployer_address)


def deploy_contracts(
    nucypher_contracts: DependencyAPI,
    test_contracts: DependencyAPI,
    accounts: List[TestAccount],
):
    """Deploy contracts o via ape's API for testing."""
    config = ape_config.get_config("deployments")["ethereum"]["local"]
    deployments = dict()
    for name in _CONTRACTS_TO_DEPLOY_ON_TESTERCHAIN:
        params, deployer_account = get_deployment_params(
            name, deployments=deployments, config=config, accounts=accounts
        )
        try:
            # this contract is a dependency
            contract = getattr(nucypher_contracts, name)
        except AttributeError:
            # this contract is local to this project
            contract = getattr(project, name)
        deployed_contract = deployer_account.deploy(contract, *params.values())
        deployments[name] = deployed_contract
    return deployments


def registry_from_ape_deployments(
    nucypher_contracts: DependencyAPI, deployments: Dict[str, ContractInstance]
) -> InMemoryContractRegistry:
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
