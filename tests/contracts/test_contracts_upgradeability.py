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

import pytest
import requests
from eth_utils import to_wei

from constant_sorrow import constants
from web3.exceptions import ValidationError

from nucypher.blockchain.economics import Economics
from nucypher.blockchain.eth.agents import StakingEscrowAgent, WorkLockAgent
from nucypher.blockchain.eth.deployers import (
    AdjudicatorDeployer,
    BaseContractDeployer,
    NucypherTokenDeployer,
    PolicyManagerDeployer,
    StakingEscrowDeployer,
    WorklockDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, BaseContractRegistry
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.sol.compile.constants import SOLIDITY_SOURCE_ROOT, TEST_SOLIDITY_SOURCE_ROOT
from nucypher.blockchain.eth.sol.compile.types import SourceBundle
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.fixtures import make_token_economics
from tests.utils.blockchain import free_gas_price_strategy, TesterBlockchain

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


def parameters_v611(blockchain_interface: BlockchainDeployerInterface,
                    transacting_power: TransactingPower,
                    deployer: BaseContractDeployer):
    policy_manager_mock, _ = blockchain_interface.deploy_contract(
        transacting_power,
        deployer.registry,
        "OldPolicyManagerMock"
    )
    adjudicator_mock, _ = blockchain_interface.deploy_contract(
        transacting_power,
        deployer.registry,
        "OldAdjudicatorMock"
    )
    parameters = {
        "_genesisHoursPerPeriod": 1,
        "_hoursPerPeriod": 1,
        "_issuanceDecayCoefficient": 1,
        "_lockDurationCoefficient1": 1,
        "_lockDurationCoefficient2": 2,
        "_maximumRewardedPeriods": 1,
        "_firstPhaseTotalSupply": 1,
        "_firstPhaseMaxIssuance": 1,
        "_minLockedPeriods": 2,
        "_minAllowableLockedTokens": 0,
        "_maxAllowableLockedTokens": deployer.economics.maximum_allowed_locked,
        "_minWorkerPeriods": 1,
        "_policyManager": policy_manager_mock.address,
        "_adjudicator": adjudicator_mock.address
      }
    return parameters


# Constructor parameters overrides for previous versions if needed
# All versions below the specified version must use these overrides
# 'None' value removes arg from list of constructor parameters
CONSTRUCTOR_OVERRIDES = {
    StakingEscrowDeployer.contract_name: {
        "v5.7.1": lambda *args: {"_genesisHoursPerPeriod": None},
        "v6.1.1": parameters_v611
    }
}

FORCE_SKIP = {
    StakingEscrowDeployer.contract_name: ["v5.6.1", "v6.2.1"],
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
            overrides_func = CONSTRUCTOR_OVERRIDES[contract_name][latest_version]
            overrides = overrides_func(blockchain_interface,
                                       transacting_power,
                                       deployer)
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


def prepare_staker(blockchain_interface: TesterBlockchain,
                   deployer: StakingEscrowDeployer,
                   transacting_power: TransactingPower):
    worklock_agent = WorkLockAgent(registry=deployer.registry)
    value = worklock_agent.minimum_allowed_bid
    worklock_agent.bid(value=value, transacting_power=transacting_power)
    blockchain_interface.time_travel(hours=100)
    worklock_agent.verify_bidding_correctness(transacting_power=transacting_power, gas_limit=1000000)
    worklock_agent.claim(transacting_power=transacting_power)


def test_upgradeability(temp_dir_path):
    # Prepare remote source for compilation
    download_github_dir(GITHUB_SOURCE_LINK, temp_dir_path)

    # Prepare the blockchain
    TesterBlockchain.SOURCES = [
        SourceBundle(base_path=SOLIDITY_SOURCE_ROOT,
                     other_paths=(TEST_SOLIDITY_SOURCE_ROOT,)),
        SourceBundle(base_path=Path(temp_dir_path))
    ]

    provider_uri = 'tester://pyevm/2'  # TODO: Testerchain caching Issues
    try:
        blockchain_interface = TesterBlockchain(gas_strategy='free')
        blockchain_interface.provider_uri = provider_uri
        blockchain_interface.connect()
        origin = blockchain_interface.client.accounts[0]
        BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)
        transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                             signer=Web3Signer(blockchain_interface.client),
                                             account=origin)

        economics = make_token_economics(blockchain_interface)

        # Check contracts with multiple versions
        contract_name = StakingEscrowDeployer.contract_name
        skip_staking_escrow_test = skip_test(blockchain_interface, contract_name)

        if skip_staking_escrow_test:
            return

        # Prepare master version of contracts and upgrade to the latest
        registry = InMemoryContractRegistry()

        token_deployer = NucypherTokenDeployer(registry=registry, economics=economics)
        token_deployer.deploy(transacting_power=transacting_power)

        staking_escrow_deployer = StakingEscrowDeployer(registry=registry, economics=economics)
        staking_escrow_deployer.deploy(deployment_mode=constants.INIT, transacting_power=transacting_power)

        if not skip_staking_escrow_test:
            economics.worklock_supply = economics.maximum_allowed_locked
            worklock_deployer = WorklockDeployer(registry=registry, economics=economics)
            worklock_deployer.deploy(transacting_power=transacting_power)

        staking_escrow_deployer = StakingEscrowDeployer(registry=registry, economics=economics)
        deploy_base_contract(blockchain_interface, staking_escrow_deployer,
                             transacting_power=transacting_power,
                             skipt_test=skip_staking_escrow_test)

        if not skip_staking_escrow_test:
            prepare_staker(blockchain_interface=blockchain_interface,
                           deployer=staking_escrow_deployer,
                           transacting_power=transacting_power)
            staking_escrow_deployer.upgrade(transacting_power=transacting_power,
                                            contract_version="latest",
                                            confirmations=0)

    finally:
        # Unregister interface  # TODO: Move to method?
        with contextlib.suppress(KeyError):
            del BlockchainInterfaceFactory._interfaces[provider_uri]
