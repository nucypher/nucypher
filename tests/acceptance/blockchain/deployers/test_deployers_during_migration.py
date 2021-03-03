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
import pytest

from constant_sorrow import constants

from constant_sorrow.constants import BARE
from nucypher.blockchain.economics import StandardTokenEconomics

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, PolicyManagerAgent
from nucypher.blockchain.eth.deployers import (StakingEscrowDeployer, PolicyManagerDeployer)


@pytest.fixture(scope="module")
def new_token_economics(token_economics):
    economics = StandardTokenEconomics(genesis_hours_per_period=token_economics.hours_per_period,
                                       hours_per_period=2 * token_economics.hours_per_period)
    return economics


@pytest.fixture(scope='module')
def baseline_deployment(staking_escrow_deployer, transacting_power):
    staking_escrow_deployer.deploy(deployment_mode=constants.FULL, transacting_power=transacting_power)


@pytest.fixture(scope='module')
def new_staking_escrow_deployer(testerchain, test_registry, new_token_economics):
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry,
                                                    economics=new_token_economics)
    return staking_escrow_deployer


@pytest.fixture(scope='module')
def new_policy_manager_deployer(testerchain, test_registry, new_token_economics):
    policy_manager_deployer = PolicyManagerDeployer(registry=test_registry,
                                                    economics=new_token_economics)
    return policy_manager_deployer


def test_staking_escrow_preparation(testerchain,
                                    transacting_power,
                                    baseline_deployment,
                                    token_economics,
                                    test_registry,
                                    new_staking_escrow_deployer):
    new_staking_escrow_deployer.deploy(deployment_mode=constants.BARE,
                                       ignore_deployed=True,
                                       transacting_power=transacting_power)

    # Data is still old, because there is no upgrade yet
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.contract.functions.secondsPerPeriod().call() == token_economics.seconds_per_period
    assert staking_agent.contract.functions.genesisSecondsPerPeriod().call() == token_economics.seconds_per_period


def test_policy_manager_preparation(testerchain,
                                    transacting_power,
                                    token_economics,
                                    test_registry,
                                    new_policy_manager_deployer):
    new_policy_manager_deployer.deploy(deployment_mode=constants.BARE,
                                       ignore_deployed=True,
                                       transacting_power=transacting_power)

    # Data is still old, because there is no upgrade yet
    policy_manager_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    assert policy_manager_agent.contract.functions.secondsPerPeriod().call() == token_economics.seconds_per_period
    assert policy_manager_agent.contract.functions.genesisSecondsPerPeriod().call() == token_economics.seconds_per_period


def test_staking_escrow_migration_upgrade(testerchain,
                                          transacting_power,
                                          test_registry,
                                          new_token_economics,
                                          new_staking_escrow_deployer):
    latest_staking_escrow = testerchain.get_contract_by_name(registry=test_registry,
                                                             contract_name=new_staking_escrow_deployer.contract_name,
                                                             enrollment_version='latest')

    new_staking_escrow_deployer.retarget(target_address=latest_staking_escrow.address,
                                         confirmations=0,
                                         transacting_power=transacting_power)

    # Now data must be new
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.contract.functions.secondsPerPeriod().call() == new_token_economics.seconds_per_period
    assert staking_agent.contract.functions.genesisSecondsPerPeriod().call() == new_token_economics.genesis_seconds_per_period


def test_policy_manager_migration_upgrade(testerchain,
                                          transacting_power,
                                          test_registry,
                                          new_token_economics,
                                          new_policy_manager_deployer):
    latest_policy_manager = testerchain.get_contract_by_name(registry=test_registry,
                                                             contract_name=new_policy_manager_deployer.contract_name,
                                                             enrollment_version='latest')

    new_policy_manager_deployer.retarget(target_address=latest_policy_manager.address,
                                         confirmations=0,
                                         transacting_power=transacting_power)

    # Now data must be new
    policy_manager_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    assert policy_manager_agent.contract.functions.secondsPerPeriod().call() == new_token_economics.seconds_per_period
    assert policy_manager_agent.contract.functions.genesisSecondsPerPeriod().call() == new_token_economics.genesis_seconds_per_period
