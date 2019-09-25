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

from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor
from nucypher.utilities.sandbox.constants import DEVELOPMENT_ETH_AIRDROP_AMOUNT


@pytest.fixture(scope='module')
def policy_author(testerchain, test_registry):
    alice = testerchain.unassigned_accounts[3]
    policy_author = BlockchainPolicyAuthor(checksum_address=alice, registry=test_registry)
    return policy_author


@pytest.mark.slow()
@pytest.fixture(scope='module')
def author(testerchain, agency, test_registry):
    _origin, ursula, alice, *everybody_else = testerchain.client.accounts
    author = BlockchainPolicyAuthor(checksum_address=alice, registry=test_registry)
    return author


@pytest.mark.slow()
def test_create_policy_author(testerchain, agency, test_registry):
    _origin, ursula, alice, *everybody_else = testerchain.client.accounts
    policy_author = BlockchainPolicyAuthor(checksum_address=alice, registry=test_registry)
    assert policy_author.checksum_address == alice


def test_policy_author_create_policy(policy_author):
    label, rate, duration, first_period_reward = b'llamas', 100, 1, 1
    policy = policy_author.create_policy(label=label, rate=100, duration_periods=1, first_period_reward=1)
    assert policy.rate == rate
    assert policy.label == label
    assert policy.duration_periods == duration
    assert policy.first_period_reward == first_period_reward


def test_policy_author_read_published_policies(testerchain, policy_author, stakers, blockchain_alice):

    staker = stakers.pop()

    # Mock Policy Publish
    policy_agent = policy_author.policy_agent
    policy_id = os.urandom(16)
    receipt = policy_agent.create_policy(
        policy_id=policy_id,
        author_address=policy_author.checksum_address,
        value=1000,
        periods=1,
        first_period_reward=10,
        node_addresses=[staker.checksum_address]
    )
    assert receipt['status'] == 1

    # Mock known nodes and label
    policy_author.known_nodes = blockchain_alice.known_nodes
    label = b'llama-label'

    # Read
    policy_author.read_policy(policy_id, label=label)
    assert len(policy_author.policies) == 1
