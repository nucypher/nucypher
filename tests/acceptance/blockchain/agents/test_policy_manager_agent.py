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


import collections

import os
import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import is_checksum_address, to_wei

from nucypher.blockchain.eth.agents import ContractAgency, PolicyManagerAgent
from tests.constants import FEE_RATE_RANGE, INSECURE_DEVELOPMENT_PASSWORD

MockPolicyMetadata = collections.namedtuple('MockPolicyMetadata', 'policy_id author addresses')


@pytest.fixture(scope='function')
def policy_meta(testerchain, agency, token_economics, blockchain_ursulas):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    _policy_id = os.urandom(16)
    staker_addresses = list(staking_agent.get_stakers_reservoir(duration=1).draw(3))
    number_of_periods = 10
    now = testerchain.w3.eth.getBlock('latest').timestamp
    _txhash = agent.create_policy(policy_id=_policy_id,
                                  author_address=testerchain.alice_account,
                                  value=to_wei(1, 'gwei') * len(staker_addresses) * number_of_periods,
                                  end_timestamp=now + (number_of_periods - 1) * token_economics.hours_per_period * 60 * 60,
                                  node_addresses=staker_addresses)

    return MockPolicyMetadata(_policy_id, testerchain.alice_account, staker_addresses)



@pytest.mark.usefixtures('blockchain_ursulas')
def test_create_policy(testerchain, agency, token_economics, mock_transacting_power_activation):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    mock_transacting_power_activation(account=testerchain.alice_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    policy_id = os.urandom(16)
    node_addresses = list(staking_agent.get_stakers_reservoir(duration=1).draw(3))
    now = testerchain.w3.eth.getBlock('latest').timestamp
    receipt = agent.create_policy(policy_id=policy_id,
                                  author_address=testerchain.alice_account,
                                  value=token_economics.minimum_allowed_locked,
                                  end_timestamp=now + 10 * token_economics.hours_per_period * 60,
                                  node_addresses=node_addresses)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address



@pytest.mark.usefixtures('blockchain_ursulas')
def test_fetch_policy_arrangements(agency, policy_meta):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    arrangements = list(agent.fetch_policy_arrangements(policy_id=policy_meta.policy_id))
    assert arrangements
    assert len(arrangements) == len(policy_meta.addresses)
    assert is_checksum_address(arrangements[0][0])
    assert list(record[0] for record in arrangements) == policy_meta.addresses



@pytest.mark.usefixtures('blockchain_ursulas')
def test_revoke_arrangement(agency, policy_meta):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    receipt = agent.revoke_arrangement(policy_id=policy_meta.policy_id,
                                       author_address=policy_meta.author,
                                       node_address=policy_meta.addresses[0])
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address



@pytest.mark.usefixtures('blockchain_ursulas')
def test_revoke_policy(agency, policy_meta):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    receipt = agent.revoke_policy(policy_id=policy_meta.policy_id, author_address=policy_meta.author)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.usefixtures('blockchain_ursulas')
def test_calculate_refund(testerchain, agency, policy_meta, mock_transacting_power_activation):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    staker = policy_meta.addresses[-1]
    worker = staking_agent.get_worker_from_staker(staker)

    mock_transacting_power_activation(account=worker, password=INSECURE_DEVELOPMENT_PASSWORD)

    testerchain.time_travel(hours=9)
    staking_agent.commit_to_next_period(worker_address=worker)

    mock_transacting_power_activation(account=testerchain.alice_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    receipt = agent.calculate_refund(policy_id=policy_meta.policy_id, author_address=policy_meta.author)
    assert receipt['status'] == 1, "Transaction Rejected"


@pytest.mark.usefixtures('blockchain_ursulas')
def test_collect_refund(testerchain, agency, policy_meta):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    testerchain.time_travel(hours=9)
    receipt = agent.collect_refund(policy_id=policy_meta.policy_id, author_address=policy_meta.author)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


def test_set_min_fee_rate(testerchain, test_registry, agency, policy_meta):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)  # type: PolicyManagerAgent
    minimum, default, maximum = FEE_RATE_RANGE
    staker = policy_meta.addresses[-1]

    assert policy_agent.get_min_fee_rate(staker) == default
    with pytest.raises((TransactionFailed, ValueError)):
        policy_agent.set_min_fee_rate(staker_address=staker, min_rate=minimum - 1)

    receipt = policy_agent.set_min_fee_rate(staker_address=staker, min_rate=minimum + 1)
    assert receipt['status'] == 1
    assert policy_agent.get_min_fee_rate(staker) == minimum + 1



@pytest.mark.usefixtures('blockchain_ursulas')
def test_collect_policy_fee(testerchain, agency, policy_meta, token_economics, mock_transacting_power_activation):
    token_agent, staking_agent, policy_agent = agency
    agent = policy_agent

    staker = policy_meta.addresses[-1]
    worker = staking_agent.get_worker_from_staker(staker)

    mock_transacting_power_activation(account=worker, password=INSECURE_DEVELOPMENT_PASSWORD)

    old_eth_balance = token_agent.blockchain.client.get_balance(staker)

    for _ in range(token_economics.minimum_locked_periods):
        staking_agent.commit_to_next_period(worker_address=worker)
        testerchain.time_travel(periods=1)

    mock_transacting_power_activation(account=staker, password=INSECURE_DEVELOPMENT_PASSWORD)
    receipt = agent.collect_policy_fee(collector_address=staker, staker_address=staker)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address
    new_eth_balance = token_agent.blockchain.client.get_balance(staker)
    assert new_eth_balance > old_eth_balance
