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

from nucypher.blockchain.eth.constants import POLICY_ID_LENGTH
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.agents import ContractAgency, PolicyManagerAgent, StakingEscrowAgent, NucypherTokenAgent
from tests.constants import FEE_RATE_RANGE

MockPolicyMetadata = collections.namedtuple('MockPolicyMetadata', 'policy_id author addresses')


@pytest.fixture(scope='function')
def policy_meta(testerchain, agency, token_economics, blockchain_ursulas, test_registry):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    _policy_id = os.urandom(POLICY_ID_LENGTH)
    staker_addresses = list(staking_agent.get_stakers_reservoir(duration=1).draw(3))
    number_of_periods = 10
    now = testerchain.w3.eth.getBlock('latest').timestamp
    tpower = TransactingPower(account=testerchain.alice_account, signer=Web3Signer(testerchain.client))
    _txhash = policy_agent.create_policy(policy_id=_policy_id,
                                         transacting_power=tpower,
                                         value=to_wei(1, 'gwei') * len(staker_addresses) * number_of_periods,
                                         end_timestamp=now + (number_of_periods - 1) * token_economics.hours_per_period * 60 * 60,
                                         node_addresses=staker_addresses)

    return MockPolicyMetadata(policy_id=_policy_id, author=tpower, addresses=staker_addresses)



@pytest.mark.usefixtures('blockchain_ursulas')
def test_create_policy(testerchain, agency, token_economics, test_registry):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    policy_id = os.urandom(POLICY_ID_LENGTH)
    node_addresses = list(staking_agent.get_stakers_reservoir(duration=1).draw(3))
    now = testerchain.w3.eth.getBlock('latest').timestamp
    tpower = TransactingPower(account=testerchain.alice_account, signer=Web3Signer(testerchain.client))
    receipt = policy_agent.create_policy(policy_id=policy_id,
                                         transacting_power=tpower,
                                         value=token_economics.minimum_allowed_locked,
                                         end_timestamp=now + 10 * token_economics.hours_per_period * 60,
                                         node_addresses=node_addresses)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == policy_agent.contract_address


@pytest.mark.usefixtures('blockchain_ursulas')
def test_fetch_policy_arrangements(agency, policy_meta, test_registry):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    arrangements = list(policy_agent.fetch_policy_arrangements(policy_id=policy_meta.policy_id))
    assert arrangements
    assert len(arrangements) == len(policy_meta.addresses)
    assert is_checksum_address(arrangements[0][0])
    assert list(record[0] for record in arrangements) == policy_meta.addresses


@pytest.mark.usefixtures('blockchain_ursulas')
def test_revoke_arrangement(agency, policy_meta, test_registry):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    receipt = policy_agent.revoke_arrangement(policy_id=policy_meta.policy_id,
                                              transacting_power=policy_meta.author,
                                              node_address=policy_meta.addresses[0])
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == policy_agent.contract_address



@pytest.mark.usefixtures('blockchain_ursulas')
def test_revoke_policy(agency, policy_meta, test_registry):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    receipt = policy_agent.revoke_policy(policy_id=policy_meta.policy_id, transacting_power=policy_meta.author)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == policy_agent.contract_address


@pytest.mark.usefixtures('blockchain_ursulas')
def test_calculate_refund(testerchain, agency, policy_meta, test_registry):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)

    staker = policy_meta.addresses[-1]
    worker = staking_agent.get_worker_from_staker(staker)

    testerchain.time_travel(hours=9)
    worker_power = TransactingPower(account=worker, signer=Web3Signer(testerchain.client))
    staking_agent.commit_to_next_period(transacting_power=worker_power)

    receipt = policy_agent.calculate_refund(policy_id=policy_meta.policy_id, transacting_power=policy_meta.author)
    assert receipt['status'] == 1, "Transaction Rejected"


@pytest.mark.usefixtures('blockchain_ursulas')
def test_collect_refund(testerchain, agency, policy_meta, test_registry):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    testerchain.time_travel(hours=9)
    receipt = policy_agent.collect_refund(policy_id=policy_meta.policy_id, transacting_power=policy_meta.author)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == policy_agent.contract_address


def test_set_min_fee_rate(testerchain, test_registry, agency, policy_meta):
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    minimum, default, maximum = FEE_RATE_RANGE
    staker = policy_meta.addresses[-1]
    tpower = TransactingPower(account=staker, signer=Web3Signer(testerchain.client))

    assert policy_agent.get_min_fee_rate(staker) == default
    with pytest.raises((TransactionFailed, ValueError)):
        policy_agent.set_min_fee_rate(transacting_power=tpower, min_rate=minimum - 1)

    receipt = policy_agent.set_min_fee_rate(transacting_power=tpower, min_rate=minimum + 1)
    assert receipt['status'] == 1
    assert policy_agent.get_min_fee_rate(staker) == minimum + 1


@pytest.mark.usefixtures('blockchain_ursulas')
def test_collect_policy_fee(testerchain, agency, policy_meta, token_economics, test_registry):
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)

    staker = policy_meta.addresses[-1]
    worker = staking_agent.get_worker_from_staker(staker)
    worker_power = TransactingPower(account=worker, signer=Web3Signer(testerchain.client))


    old_eth_balance = token_agent.blockchain.client.get_balance(staker)
    for _ in range(token_economics.minimum_locked_periods):
        testerchain.time_travel(periods=1)
        staking_agent.commit_to_next_period(transacting_power=worker_power)

    staker_power = TransactingPower(account=staker, signer=Web3Signer(testerchain.client))
    receipt = policy_agent.collect_policy_fee(collector_address=staker, transacting_power=staker_power)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == policy_agent.contract_address
    new_eth_balance = token_agent.blockchain.client.get_balance(staker)
    assert new_eth_balance > old_eth_balance
