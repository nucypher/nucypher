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
from eth_tester.exceptions import TransactionFailed

from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import ContractAgency, NucypherTokenAgent, StakingEscrowAgent
from nucypher.blockchain.eth.deployers import (AdjudicatorDeployer, BaseContractDeployer, NucypherTokenDeployer,
                                               PolicyManagerDeployer, StakingEscrowDeployer)
from nucypher.crypto.powers import TransactingPower
from tests.utils.blockchain import token_airdrop
from tests.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT, INSECURE_DEVELOPMENT_PASSWORD


def test_deploy_idle_network(testerchain, deployment_progress, test_registry):
    origin, *everybody_else = testerchain.client.accounts

    #
    # Nucypher Token
    #
    token_deployer = NucypherTokenDeployer(registry=test_registry)
    tpower = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_deployed()

    token_deployer.deploy(progress=deployment_progress, transacting_power=tpower)
    assert token_deployer.is_deployed()

    token_agent = NucypherTokenAgent(registry=test_registry)
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # StakingEscrow - in INIT mode, i.e. stub for StakingEscrow
    #
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed()

    staking_escrow_deployer.deploy(progress=deployment_progress,
                                   deployment_mode=constants.INIT,
                                   transacting_power=tpower)
    assert not staking_escrow_deployer.is_deployed()

    #
    # Policy Manager
    #
    policy_manager_deployer = PolicyManagerDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_deployed()

    policy_manager_deployer.deploy(progress=deployment_progress, transacting_power=tpower)
    assert policy_manager_deployer.is_deployed()

    policy_agent = policy_manager_deployer.make_agent()
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    #
    # Adjudicator
    #
    adjudicator_deployer = AdjudicatorDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert adjudicator_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not adjudicator_deployer.is_deployed()

    adjudicator_deployer.deploy(progress=deployment_progress, transacting_power=tpower)
    assert adjudicator_deployer.is_deployed()

    adjudicator_agent = adjudicator_deployer.make_agent()
    assert adjudicator_agent.contract_address == adjudicator_deployer.contract_address

    #
    # StakingEscrow - in IDLE mode, i.e. without activation steps (approve_funding and initialize)
    #
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed()

    staking_escrow_deployer.deploy(progress=deployment_progress,
                                   deployment_mode=constants.IDLE,
                                   transacting_power=tpower)
    assert staking_escrow_deployer.is_deployed()

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.contract_address == staking_escrow_deployer.contract_address

    # The contract has no tokens yet
    assert token_agent.get_balance(staking_agent.contract_address) == 0


def test_stake_in_idle_network(testerchain, token_economics, test_registry):

    # Let's fund a staker first
    token_agent = NucypherTokenAgent(registry=test_registry)
    tpower = TransactingPower(account=testerchain.etherbase_account, signer=Web3Signer(testerchain.client))
    token_airdrop(transacting_power=tpower,
                  addresses=testerchain.stakers_accounts,
                  token_agent=token_agent,
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    account = testerchain.stakers_accounts[0]
    tpower = TransactingPower(account=account, signer=Web3Signer(testerchain.client))
    staker = Staker(transacting_power=tpower,
                    domain=TEMPORARY_DOMAIN,
                    registry=test_registry)

    # Since StakingEscrow hasn't been activated yet, deposit should work but making a commitment must fail
    amount = token_economics.minimum_allowed_locked
    periods = token_economics.minimum_locked_periods
    staker.initialize_stake(amount=amount, lock_periods=periods)
    staker.bond_worker(account)
    with pytest.raises((TransactionFailed, ValueError)):
        staker.staking_agent.commit_to_next_period(transacting_power=tpower)


def test_activate_network(testerchain, token_economics, test_registry):
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry)
    tpower = TransactingPower(account=testerchain.etherbase_account,
                              signer=Web3Signer(testerchain.client))

    # Let's check we're in the position of activating StakingEscrow
    assert staking_escrow_deployer.is_deployed()
    assert not staking_escrow_deployer.is_active
    assert staking_escrow_deployer.ready_to_activate

    # OK, let's do it!
    receipts = staking_escrow_deployer.activate(transacting_power=tpower)
    for tx in receipts:
        assert receipts[tx]['status'] == 1

    # Yay!
    assert staking_escrow_deployer.is_active

    # Trying to activate now must fail
    assert not staking_escrow_deployer.ready_to_activate
    with pytest.raises(StakingEscrowDeployer.ContractDeploymentError):
        staking_escrow_deployer.activate(transacting_power=tpower)
