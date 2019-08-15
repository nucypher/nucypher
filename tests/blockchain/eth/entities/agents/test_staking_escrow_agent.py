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

import os

import pytest
from eth_utils.address import to_checksum_address, is_address

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.slow()
def test_unknown_contract(testerchain, test_registry):
    with pytest.raises(BaseContractRegistry.UnknownContract) as exception:
        _staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    assert exception.value.args[0] == StakingEscrowAgent.registry_contract_name


@pytest.mark.slow()
def test_deposit_tokens(testerchain, agency, token_economics):
    token_agent, staking_agent, _policy_agent = agency

    locked_tokens = token_economics.minimum_allowed_locked * 5

    staker_account = testerchain.unassigned_accounts[0]

    # Mock Powerup consumption (Deployer)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=testerchain.etherbase_account)
    testerchain.transacting_power.activate()

    balance = token_agent.get_balance(address=staker_account)
    assert balance == 0

    # The staker receives an initial amount of tokens
    _txhash = token_agent.transfer(amount=token_economics.minimum_allowed_locked * 10,
                                   target_address=staker_account,
                                   sender_address=testerchain.etherbase_account)

    # Mock Powerup consumption (Ursula-Staker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=staker_account)
    testerchain.transacting_power.activate()

    #
    # Deposit: The staker deposits tokens in the StakingEscrow contract.
    # Previously, she needs to approve this transfer on the token contract.
    #

    _receipt = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked * 10,  # Approve
                                            target_address=staking_agent.contract_address,
                                            sender_address=staker_account)

    receipt = staking_agent.deposit_tokens(amount=locked_tokens,
                                           lock_periods=token_economics.minimum_locked_periods,
                                           sender_address=staker_account)

    # Check the receipt for the contract staker_address success code
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][2]['address'] == staking_agent.contract_address

    testerchain.time_travel(periods=1)
    balance = token_agent.get_balance(address=staker_account)
    assert balance == locked_tokens
    assert staking_agent.get_locked_tokens(staker_address=staker_account) == locked_tokens


@pytest.mark.slow()
def test_locked_tokens(testerchain, agency, token_economics):
    _token_agent, staking_agent, _policy_agent = agency
    staker_account = testerchain.unassigned_accounts[0]
    locked_amount = staking_agent.get_locked_tokens(staker_address=staker_account)
    assert token_economics.maximum_allowed_locked >= locked_amount >= token_economics.minimum_allowed_locked


@pytest.mark.slow()
def test_get_all_stakes(testerchain, agency, token_economics):
    _token_agent, staking_agent, _policy_agent = agency
    staker_account = testerchain.unassigned_accounts[0]

    all_stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    assert len(all_stakes) == 1
    stake_info = all_stakes[0]
    assert len(stake_info) == 3
    start_period, end_period, value = stake_info
    assert end_period > start_period
    assert token_economics.maximum_allowed_locked > value > token_economics.minimum_allowed_locked


@pytest.mark.slow()
def test_stakers_and_workers_relationships(testerchain, agency):
    _token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    # The staker hasn't set a worker yet
    assert BlockchainInterface.NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=staker_account)

    _txhash = staking_agent.set_worker(staker_address=staker_account,
                                       worker_address=worker_account)

    # We can check the staker-worker relation from both sides
    assert worker_account == staking_agent.get_worker_from_staker(staker_address=staker_account)
    assert staker_account == staking_agent.get_staker_from_worker(worker_address=worker_account)

    # No staker-worker relationship
    random_address = to_checksum_address(os.urandom(20))
    assert BlockchainInterface.NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=random_address)
    assert BlockchainInterface.NULL_ADDRESS == staking_agent.get_staker_from_worker(worker_address=random_address)


@pytest.mark.slow()
def test_get_staker_population(agency, stakers):
    _token_agent, staking_agent, _policy_agent = agency

    # Apart from all the stakers in the fixture, we also added a new staker above
    assert staking_agent.get_staker_population() == len(stakers) + 1


@pytest.mark.slow()
def test_get_swarm(agency, blockchain_ursulas):
    _token_agent, staking_agent, _policy_agent = agency

    swarm = staking_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(blockchain_ursulas) + 1

    # Grab a staker staker_address from the swarm
    staker_addr = swarm_addresses[0]
    assert isinstance(staker_addr, str)
    assert is_address(staker_addr)


@pytest.mark.slow()
@pytest.mark.usefixtures("blockchain_ursulas")
def test_sample_stakers(agency):
    _token_agent, staking_agent, _policy_agent = agency
    stakers_population = staking_agent.get_staker_population()

    with pytest.raises(StakingEscrowAgent.NotEnoughStakers):
        staking_agent.sample(quantity=stakers_population + 1, duration=1)  # One more than we have deployed

    stakers = staking_agent.sample(quantity=3, duration=5)
    assert len(stakers) == 3       # Three...
    assert len(set(stakers)) == 3  # ...unique addresses


def test_get_current_period(agency, testerchain):
    _token_agent, staking_agent,_policy_agent = agency
    start_period = staking_agent.get_current_period()
    testerchain.time_travel(periods=1)
    end_period = staking_agent.get_current_period()
    assert end_period > start_period


@pytest.mark.slow()
def test_confirm_activity(agency, testerchain):
    _token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    # Mock Powerup consumption (Ursula-Worker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=worker_account)
    testerchain.transacting_power.activate()

    receipt = staking_agent.confirm_activity(worker_address=worker_account)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == staking_agent.contract_address


@pytest.mark.skip('To be implemented')
def test_divide_stake(agency, token_economics):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.client.accounts

    stakes = list(agent.get_all_stakes(staker_address=someone))
    assert len(stakes) == 1

    # Approve
    _txhash = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked*2,
                                           target_address=agent.contract_address,
                                           sender_address=someone)

    # Deposit
    _txhash = agent.deposit_tokens(amount=token_economics.minimum_allowed_locked*2,
                                   lock_periods=token_economics.minimum_locked_periods,
                                   sender_address=someone)

    # Confirm Activity
    _txhash = agent.confirm_activity(node_address=someone)
    testerchain.time_travel(periods=1)

    receipt = agent.divide_stake(staker_address=someone,
                                 stake_index=1,
                                 target_value=token_economics.minimum_allowed_locked,
                                 periods=1)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    stakes = list(agent.get_all_stakes(staker_address=someone))
    assert len(stakes) == 3


@pytest.mark.slow()
def test_collect_staking_reward(agency, testerchain):
    token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    # Confirm Activity
    _receipt = staking_agent.confirm_activity(worker_address=worker_account)
    testerchain.time_travel(periods=2)

    # Mock Powerup consumption (Ursula-Staker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=staker_account)
    testerchain.transacting_power.activate()

    # Mint
    _receipt = staking_agent.mint(staker_address=staker_account)

    old_balance = token_agent.get_balance(address=staker_account)

    receipt = staking_agent.collect_staking_reward(staker_address=staker_account)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][-1]['address'] == staking_agent.contract_address

    new_balance = token_agent.get_balance(address=staker_account)  # not the shoes
    assert new_balance > old_balance
