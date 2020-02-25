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
from eth_utils import keccak

from nucypher.blockchain.economics import StandardTokenEconomics, EconomicsFactory
from nucypher.blockchain.eth.actors import Staker, Bidder
from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.constants import WORKLOCK_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import WorklockDeployer, StakingInterfaceDeployer, AdjudicatorDeployer
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import STAKING_ESCROW_DEPLOYMENT_SECRET, INSECURE_DEPLOYMENT_SECRET_HASH, \
    POLICY_MANAGER_DEPLOYMENT_SECRET, INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='module')
def baseline_deployment(adjudicator_deployer):
    adjudicator_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)


@pytest.fixture(scope="module")
def worklock_deployer(baseline_deployment,
                      testerchain,
                      test_registry,
                      token_economics):
    worklock_deployer = WorklockDeployer(registry=test_registry,
                                         economics=token_economics,
                                         deployer_address=testerchain.etherbase_account)
    return worklock_deployer


def test_worklock_deployment(worklock_deployer,
                             baseline_deployment,
                             staking_escrow_deployer,
                             deployment_progress,
                             test_registry,
                             testerchain):

    # Ensure nucypher APIs implementing economics are usable without a worklock deployment.
    economics = EconomicsFactory.retrieve_from_blockchain(registry=test_registry)
    assert economics.bidding_start_date == NotImplemented

    # Deploy
    assert worklock_deployer.contract_name == WORKLOCK_CONTRACT_NAME
    deployment_receipts = worklock_deployer.deploy(progress=deployment_progress)    # < ---- DEPLOY

    # Verify economics are updated
    economics = EconomicsFactory.retrieve_from_blockchain(registry=test_registry)
    assert economics.bidding_start_date != NotImplemented

    # deployment steps must match expected number of steps
    steps = worklock_deployer.deployment_steps
    assert deployment_progress.num_steps == len(steps) == len(deployment_receipts) == 4

    # Ensure every step is successful
    for step_title in steps:
        assert deployment_receipts[step_title]['status'] == 1

    # Ensure the correct staking escrow address is set
    staking_escrow_address = worklock_deployer.contract.functions.escrow().call()
    assert staking_escrow_deployer.contract_address == staking_escrow_address


def test_make_agent(worklock_deployer, test_registry):

    agent = worklock_deployer.make_agent()

    # Retrieve the PolicyManagerAgent singleton
    another_worklock_agent = WorkLockAgent(registry=test_registry)
    assert agent == another_worklock_agent  # __eq__

    # Compare the contract address for equality
    assert agent.contract_address == another_worklock_agent.contract_address


def test_deployment_parameters(worklock_deployer, test_registry, token_economics):

    # Ensure restoration of deployment parameters
    agent = worklock_deployer.make_agent()
    params = agent.worklock_parameters()
    supply, start, end, end_cancellation, boost, locktime, min_bid = params
    assert token_economics.worklock_supply == supply
    assert token_economics.bidding_start_date == start
    assert token_economics.bidding_end_date == end
    assert token_economics.cancellation_end_date == end_cancellation
    assert token_economics.worklock_boosting_refund_rate == boost
    assert token_economics.worklock_commitment_duration == locktime
    assert token_economics.worklock_min_allowed_bid == min_bid
