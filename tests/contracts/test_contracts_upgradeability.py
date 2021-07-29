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
from pathlib import Path

import requests
from constant_sorrow import constants
from web3.exceptions import ValidationError

from nucypher.blockchain.eth.deployers import (
    AdjudicatorDeployer,
    BaseContractDeployer,
    NucypherTokenDeployer,
    PolicyManagerDeployer,
    StakingEscrowDeployer,
    WorklockDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.sol.compile.constants import SOLIDITY_SOURCE_ROOT
from nucypher.blockchain.eth.sol.compile.types import SourceBundle
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.fixtures import make_token_economics
from tests.utils.blockchain import free_gas_price_strategy

USER = "nucypher"
REPO = "nucypher"
BRANCH = "main"
GITHUB_SOURCE_LINK = f"https://api.github.com/repos/{USER}/{REPO}/contents/nucypher/blockchain/eth/sol/source?ref={BRANCH}"


BlockchainDeployerInterface.GAS_STRATEGIES = {**BlockchainDeployerInterface.GAS_STRATEGIES,
                                              'free': free_gas_price_strategy}


def download_github_dir(source_link: str, target_folder: Path):
    response = requests.get(source_link)
    if response.status_code != 200:
        error = f"Failed to call api {source_link} with status code {response.status_code}"
        raise RuntimeError(error)

    for content in response.json():
        path = target_folder / content["name"]
        if content["type"] == "dir":
            path.mkdir()
            download_github_dir(content["url"], path)
        else:
            download_github_file(content["download_url"], path)


def download_github_file(source_link: str, target_folder: Path):
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
                                                     "_rewardedPeriods": 1},
                                          "v5.7.1": {"_genesisHoursPerPeriod": None}
                                          }
}

FORCE_SKIP = {
    StakingEscrowDeployer.contract_name: ["v5.6.1"],
    PolicyManagerDeployer.contract_name: ["v6.2.1"]
}


def deploy_base_contract(blockchain_interface: BlockchainDeployerInterface,
                         deployer: BaseContractDeployer,
                         transacting_power: TransactingPower,
                         skipt_test: bool):
    contract_name = deployer.contract_name
    latest_version, _data = blockchain_interface.find_raw_contract_data(contract_name, "latest")
    raw_contracts = blockchain_interface._raw_contract_cache
    overrides = dict()
    if len(raw_contracts[contract_name]) != 1:
        try:
            overrides = CONSTRUCTOR_OVERRIDES[contract_name][latest_version]
        except KeyError:
            pass

    version = "latest" if skipt_test else "earliest"
    try:
        deployer.deploy(transacting_power=transacting_power,
                        contract_version=version,
                        deployment_mode=constants.FULL, **overrides)
    except ValidationError:
        pass  # Skip errors related to initialization


def skip_test(blockchain_interface: BlockchainDeployerInterface, contract_name: str):
    latest_version, _data = blockchain_interface.find_raw_contract_data(contract_name, "latest")
    raw_contracts = blockchain_interface._raw_contract_cache
    try:
        force_skip = latest_version in FORCE_SKIP[contract_name]
    except KeyError:
        force_skip = False

    return force_skip or len(raw_contracts[contract_name]) == 1


def test_upgradeability(temp_dir_path):
    # Prepare remote source for compilation
    download_github_dir(GITHUB_SOURCE_LINK, temp_dir_path)

    # Prepare the blockchain
    BlockchainDeployerInterface.SOURCES = [
        SourceBundle(base_path=SOLIDITY_SOURCE_ROOT),
        SourceBundle(base_path=Path(temp_dir_path))
    ]

    provider_uri = 'tester://pyevm/2'  # TODO: Testerchain caching Issues
    try:
        blockchain_interface = BlockchainDeployerInterface(provider_uri=provider_uri, gas_strategy='free')
        blockchain_interface.connect()
        origin = blockchain_interface.client.accounts[0]
        BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)
        transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                             signer=Web3Signer(blockchain_interface.client),
                                             account=origin)

        economics = make_token_economics(blockchain_interface)

        # Check contracts with multiple versions
        contract_name = AdjudicatorDeployer.contract_name
        skip_adjudicator_test = skip_test(blockchain_interface, contract_name)
        contract_name = StakingEscrowDeployer.contract_name
        skip_staking_escrow_test = skip_test(blockchain_interface, contract_name)
        contract_name = PolicyManagerDeployer.contract_name
        skip_policy_manager_test = skip_test(blockchain_interface, contract_name)

        if skip_adjudicator_test and skip_staking_escrow_test and skip_policy_manager_test:
            return

        # Prepare master version of contracts and upgrade to the latest
        registry = InMemoryContractRegistry()

        token_deployer = NucypherTokenDeployer(registry=registry, economics=economics)
        token_deployer.deploy(transacting_power=transacting_power)

        staking_escrow_deployer = StakingEscrowDeployer(registry=registry, economics=economics)
        staking_escrow_deployer.deploy(deployment_mode=constants.INIT, transacting_power=transacting_power)

        policy_manager_deployer = PolicyManagerDeployer(registry=registry, economics=economics)
        deploy_base_contract(blockchain_interface, policy_manager_deployer,
                             transacting_power=transacting_power,
                             skipt_test=skip_policy_manager_test)

        adjudicator_deployer = AdjudicatorDeployer(registry=registry, economics=economics)
        deploy_base_contract(blockchain_interface, adjudicator_deployer,
                             transacting_power=transacting_power,
                             skipt_test=skip_adjudicator_test)

        if skip_staking_escrow_test:
            worklock_deployer = WorklockDeployer(registry=registry, economics=economics)
            worklock_deployer.deploy(transacting_power=transacting_power)

        staking_escrow_deployer = StakingEscrowDeployer(registry=registry, economics=economics)
        deploy_base_contract(blockchain_interface, staking_escrow_deployer,
                             transacting_power=transacting_power,
                             skipt_test=skip_staking_escrow_test)

        if not skip_staking_escrow_test:
            # TODO prepare at least one staker before calling upgrade
            staking_escrow_deployer.upgrade(transacting_power=transacting_power,
                                            contract_version="latest",
                                            confirmations=0)

        if not skip_policy_manager_test:
            policy_manager_deployer.upgrade(transacting_power=transacting_power,
                                            contract_version="latest",
                                            confirmations=0)

        if not skip_adjudicator_test:
            adjudicator_deployer.upgrade(transacting_power=transacting_power,
                                         contract_version="latest",
                                         confirmations=0)

    finally:
        # Unregister interface  # TODO: Move to method?
        with contextlib.suppress(KeyError):
            del BlockchainInterfaceFactory._interfaces[provider_uri]
