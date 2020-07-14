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
import contextlib

import os
import pytest
import requests
from web3.exceptions import ValidationError

from nucypher.blockchain.eth.deployers import AdjudicatorDeployer, BaseContractDeployer, NucypherTokenDeployer, \
    PolicyManagerDeployer, StakingEscrowDeployer
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler, SourceDirs
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

USER = "nucypher"
REPO = "nucypher"
BRANCH = "main"
GITHUB_SOURCE_LINK = f"https://api.github.com/repos/{USER}/{REPO}/contents/nucypher/blockchain/eth/sol/source?ref={BRANCH}"


def download_github_dir(source_link: str, target_folder: str):
    response = requests.get(source_link)
    if response.status_code != 200:
        error = f"Failed to call api {source_link} with status code {response.status_code}"
        raise RuntimeError(error)

    for content in response.json():
        path = os.path.join(target_folder, content["name"])
        if content["type"] == "dir":
            os.mkdir(path)
            download_github_dir(content["url"], path)
        else:
            download_github_file(content["download_url"], path)


def download_github_file(source_link: str, target_folder: str):
    response = requests.get(source_link)
    if response.status_code != 200:
        error = f"Failed to call api {source_link} with status code {response.status_code}"
        raise RuntimeError(error)

    raw_data = response.content
    with open(target_folder, 'wb') as registry_file:
        registry_file.seek(0)
        registry_file.write(raw_data)
        registry_file.truncate()


# Constructor parameters overrides for previous versions if needed
# All versions below the specified version must use these overrides
# 'None' value removes arg from list of constructor parameters
CONSTRUCTOR_OVERRIDES = {
    StakingEscrowDeployer.contract_name: {"v4.2.1": {"_issuanceDecayCoefficient": None,
                                                     "_lockDurationCoefficient1": None,
                                                     "_lockDurationCoefficient2": None,
                                                     "_maximumRewardedPeriods": None,
                                                     "_firstPhaseTotalSupply": None,
                                                     "_firstPhaseMaxIssuance": None,
                                                     "_miningCoefficient": 2,
                                                     "_lockedPeriodsCoefficient": 1,
                                                     "_rewardedPeriods": 1}}
}


def deploy_earliest_contract(blockchain_interface: BlockchainDeployerInterface,
                             deployer: BaseContractDeployer):
    contract_name = deployer.contract_name
    latest_version, _data = blockchain_interface.find_raw_contract_data(contract_name, "latest")
    try:
        overrides = CONSTRUCTOR_OVERRIDES[contract_name][latest_version]
    except KeyError:
        overrides = dict()
    try:
        deployer.deploy(contract_version="earliest", **overrides)
    except ValidationError:
        pass  # Skip errors related to initialization


def test_upgradeability(temp_dir_path, token_economics):
    # Prepare remote source for compilation
    download_github_dir(GITHUB_SOURCE_LINK, temp_dir_path)
    solidity_compiler = SolidityCompiler(source_dirs=[SourceDirs(SolidityCompiler.default_contract_dir()),
                                                      SourceDirs(temp_dir_path)])

    # Prepare the blockchain
    provider_uri = 'tester://pyevm/2'
    try:
        blockchain_interface = BlockchainDeployerInterface(provider_uri=provider_uri, compiler=solidity_compiler)
        blockchain_interface.connect()
        origin = blockchain_interface.client.accounts[0]
        BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)
        blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
        blockchain_interface.transacting_power.activate()

        # Check contracts with multiple versions
        raw_contracts = blockchain_interface._raw_contract_cache
        contract_name = AdjudicatorDeployer.contract_name
        test_adjudicator = len(raw_contracts[contract_name]) > 1
        contract_name = StakingEscrowDeployer.contract_name
        test_staking_escrow = len(raw_contracts[contract_name]) > 1
        contract_name = PolicyManagerDeployer.contract_name
        test_policy_manager = len(raw_contracts[contract_name]) > 1

        if not test_adjudicator and not test_staking_escrow and not test_policy_manager:
            return

        # Prepare master version of contracts and upgrade to the latest
        registry = InMemoryContractRegistry()

        token_deployer = NucypherTokenDeployer(registry=registry, deployer_address=origin)
        token_deployer.deploy()

        staking_escrow_deployer = StakingEscrowDeployer(registry=registry, deployer_address=origin)
        deploy_earliest_contract(blockchain_interface, staking_escrow_deployer)
        if test_staking_escrow:
            staking_escrow_deployer.upgrade(contract_version="latest")

        if test_policy_manager:
            policy_manager_deployer = PolicyManagerDeployer(registry=registry, deployer_address=origin)
            deploy_earliest_contract(blockchain_interface, policy_manager_deployer)
            policy_manager_deployer.upgrade(contract_version="latest")

        if test_adjudicator:
            adjudicator_deployer = AdjudicatorDeployer(registry=registry, deployer_address=origin)
            deploy_earliest_contract(blockchain_interface, adjudicator_deployer)
            adjudicator_deployer.upgrade(contract_version="latest")

    finally:
        # Unregister interface
        with contextlib.suppress(KeyError):
            del BlockchainInterfaceFactory._interfaces[provider_uri]
