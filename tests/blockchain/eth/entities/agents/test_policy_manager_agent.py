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

import collections
import pytest
from eth_utils import is_checksum_address


MockPolicyMetadata = collections.namedtuple('MockPolicyMetadata', 'policy_id author addresses')


@pytest.fixture(scope='function')
@pytest.mark.usefixtures('blockchain_ursulas')
def policy_meta(testerchain, agency, token_economics):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    _policy_id = os.urandom(16)
    node_addresses = list(staker_agent.sample(quantity=3, duration=1))
    _txhash = agent.create_policy(policy_id=_policy_id,
                                  author_address=testerchain.alice_account,
                                  value=token_economics.minimum_allowed_locked,
                                  periods=10,
                                  initial_reward=20,
                                  node_addresses=node_addresses)

    return MockPolicyMetadata(_policy_id, testerchain.alice_account, node_addresses)


@pytest.mark.slow()
@pytest.mark.usefixtures('blockchain_ursulas')
def test_create_policy(testerchain, agency, token_economics):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    policy_id = os.urandom(16)
    node_addresses = list(staker_agent.sample(quantity=3, duration=1))
    txhash = agent.create_policy(policy_id=policy_id,
                                 author_address=testerchain.alice_account,
                                 value=token_economics.minimum_allowed_locked,
                                 periods=10,
                                 initial_reward=20,
                                 node_addresses=node_addresses)

    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.slow()
@pytest.mark.usefixtures('blockchain_ursulas')
def test_fetch_policy_arrangements(agency, policy_meta):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    arrangements = list(agent.fetch_policy_arrangements(policy_id=policy_meta.policy_id))
    assert arrangements
    assert len(arrangements) == len(policy_meta.addresses)
    assert is_checksum_address(arrangements[0][0])
    assert list(record[0] for record in arrangements) == policy_meta.addresses


@pytest.mark.slow()
@pytest.mark.usefixtures('blockchain_ursulas')
def test_revoke_arrangement(agency, policy_meta):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    txhash = agent.revoke_arrangement(policy_id=policy_meta.policy_id,
                                      author_address=policy_meta.author,
                                      node_address=policy_meta.addresses[0])
    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.slow()
@pytest.mark.usefixtures('blockchain_ursulas')
def test_revoke_policy(agency, policy_meta):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    txhash = agent.revoke_policy(policy_id=policy_meta.policy_id, author_address=policy_meta.author)
    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.usefixtures('blockchain_ursulas')
def test_calculate_refund(testerchain, agency, policy_meta):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    ursula = policy_meta.addresses[-1]
    testerchain.time_travel(hours=9)
    _txhash = staker_agent.confirm_activity(node_address=ursula)
    txhash = agent.calculate_refund(policy_id=policy_meta.policy_id, author_address=policy_meta.author)
    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"


@pytest.mark.usefixtures('blockchain_ursulas')
def test_collect_refund(testerchain, agency, policy_meta):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    testerchain.time_travel(hours=9)
    txhash = agent.collect_refund(policy_id=policy_meta.policy_id, author_address=policy_meta.author)
    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.slow()
@pytest.mark.usefixtures('blockchain_ursulas')
def test_collect_policy_reward(testerchain, agency, policy_meta, token_economics):
    token_agent, staker_agent, policy_agent = agency
    agent = policy_agent

    ursula = policy_meta.addresses[-1]
    old_eth_balance = token_agent.blockchain.interface.w3.eth.getBalance(ursula)

    for _ in range(token_economics.minimum_locked_periods):
        _txhash = staker_agent.confirm_activity(node_address=ursula)
        testerchain.time_travel(periods=1)

    txhash = agent.collect_policy_reward(collector_address=ursula, staker_address=ursula)
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address
    new_eth_balance = token_agent.blockchain.interface.w3.eth.getBalance(ursula)
    assert new_eth_balance > old_eth_balance
