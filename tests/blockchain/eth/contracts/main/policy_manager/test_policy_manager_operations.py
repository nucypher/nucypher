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
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.interfaces import BlockchainInterface

CREATOR_FIELD = 0
RATE_FIELD = 1
START_TIMESTAMP_FIELD = 2
END_TIMESTAMP_FIELD = 3
DISABLED_FIELD = 4

REWARD_FIELD = 0
REWARD_RATE_FIELD = 1
LAST_MINED_PERIOD_FIELD = 2
MIN_REWARD_RATE_FIELD = 3

POLICY_ID_LENGTH = 16
policy_id = os.urandom(POLICY_ID_LENGTH)
policy_id_2 = os.urandom(POLICY_ID_LENGTH)
policy_id_3 = os.urandom(POLICY_ID_LENGTH)
rate = 20
one_period = 60 * 60
number_of_periods = 10
value = rate * number_of_periods


@pytest.mark.slow
def test_reward(testerchain, escrow, policy_manager):
    creator, policy_creator, bad_node, node1, node2, node3, *everyone_else = testerchain.client.accounts
    node_balance = testerchain.client.get_balance(node1)
    withdraw_log = policy_manager.events.Withdrawn.createFilter(fromBlock='latest')

    # Mint period without policies
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period - 1, 1).transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Create policy
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id, end_timestamp, [node1, node3])\
        .transact({'from': policy_creator, 'value': 2 * value})
    testerchain.wait_for_receipt(tx)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.withdraw().transact({'from': node1})
        testerchain.wait_for_receipt(tx)

    # Can't update reward directly (only through mint method in the escrow contract)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.updateReward(node1, period + 1).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    # Can't register directly (only through deposit method in the escrow contract)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.register(bad_node, period).transact({'from': bad_node})
        testerchain.wait_for_receipt(tx)

    # Mint some periods for calling updateReward method
    tx = escrow.functions.mint(period - 1, 5).transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period += 4
    assert 80 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Withdraw some ETH
    tx = policy_manager.functions.withdraw().transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert node_balance + 80 == testerchain.client.get_balance(node1)
    assert 120 + value == testerchain.client.get_balance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert node1 == event_args['node']
    assert node1 == event_args['recipient']
    assert 80 == event_args['value']

    # Mint more periods
    for x in range(6):
        tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
        period += 1
    assert 120 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]
    tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 120 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Withdraw some ETH
    tx = policy_manager.functions.withdraw(node1).transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert node_balance + value == testerchain.client.get_balance(node1)
    assert value == testerchain.client.get_balance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert node1 == event_args['node']
    assert node1 == event_args['recipient']
    assert 120 == event_args['value']

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id_2, end_timestamp, [node2, node3]) \
        .transact({'from': policy_creator, 'value': int(2 * value)})
    testerchain.wait_for_receipt(tx)

    # Mint some periods
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period, 5).transact({'from': node2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period += 5
    assert 100 == policy_manager.functions.nodes(node2).call()[REWARD_FIELD]

    # Mint more periods
    tx = escrow.functions.mint(period, 6).transact({'from': node2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period += 6
    assert 200 == policy_manager.functions.nodes(node2).call()[REWARD_FIELD]

    # Withdraw the second node reward to the first node
    node_balance = testerchain.client.get_balance(node1)
    node_2_balance = testerchain.client.get_balance(node2)
    tx = policy_manager.functions.withdraw(node1).transact({'from': node2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert node_balance + 200 == testerchain.client.get_balance(node1)
    assert node_2_balance == testerchain.client.get_balance(node2)
    assert value + 200 == testerchain.client.get_balance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert node2 == event_args['node']
    assert node1 == event_args['recipient']
    assert 200 == event_args['value']


@pytest.mark.slow
def test_refund(testerchain, escrow, policy_manager):
    creator = testerchain.client.accounts[0]
    policy_creator = testerchain.client.accounts[1]
    node1 = testerchain.client.accounts[3]
    node2 = testerchain.client.accounts[4]
    node3 = testerchain.client.accounts[5]
    creator_balance = testerchain.client.get_balance(policy_creator)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')

    # Create policy
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id, end_timestamp, [node1]) \
        .transact({'from': policy_creator, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.setLastActivePeriod(period - 1).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=8)
    # Check that methods only calculate value
    tx = policy_manager.functions.calculateRefundValue(policy_id).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.calculateRefundValue(policy_id, node1).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 200 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - 200 == testerchain.client.get_balance(policy_creator)
    assert 180 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': policy_creator})
    assert 180 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': policy_creator})

    # Call refund, the result must be almost all ETH without payment for one period
    tx = policy_manager.functions.refund(policy_id).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 20 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - 20 == testerchain.client.get_balance(policy_creator)
    assert policy_creator == policy_manager.functions.policies(policy_id).call()[CREATOR_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert 180 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert 180 == event_args['value']

    testerchain.time_travel(hours=1)
    assert 20 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': policy_creator})
    assert 20 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': policy_creator})

    # Call refund, last period must be refunded
    tx = policy_manager.functions.refund(policy_id).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance == testerchain.client.get_balance(policy_creator)
    assert policy_manager.functions.policies(policy_id).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 1 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert 20 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 1 == len(events)
    events = policy_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert 20 == event_args['value']

    # Can't refund again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, node1).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, BlockchainInterface.NULL_ADDRESS).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id).call({'from': policy_creator})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': policy_creator})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, BlockchainInterface.NULL_ADDRESS).call({'from': policy_creator})

    # Create new policy
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.setLastActivePeriod(period).transact()
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_2, end_timestamp, [node1, node2, node3]) \
        .transact({'from': policy_creator, 'value': 3 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    # Nothing to refund because nodes are active in the current period
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': policy_creator})
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': policy_creator})
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 3 * value == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - 3 * value == testerchain.client.get_balance(policy_creator)

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert 0 == event_args['value']

    event_args = events[2]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node2 == event_args['node']
    assert 0 == event_args['value']

    event_args = events[3]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node3 == event_args['node']
    assert 0 == event_args['value']

    event_args = events[4]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert 0 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert 0 == event_args['value']

    # Try to refund nonexistent policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_3).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': policy_creator})
    # Only policy owner can call refund
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': node1})

    # Mint some periods and mark others as downtime periods
    tx = escrow.functions.mint(period, 1).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    period += 1
    tx = escrow.functions.mint(period, 2).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.pushDowntimePeriod(period + 2, period + 3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint(period + 4, 1).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.pushDowntimePeriod(period + 5, period + 7).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint(period + 8, 1).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(period + 8).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 100 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    testerchain.time_travel(hours=10)
    assert 300 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': policy_creator})
    assert 100 == policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': policy_creator})

    # Refund for only inactive periods
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 2 * value + 100 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - (2 * value + 100) == testerchain.client.get_balance(policy_creator)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert 100 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)

    # Can't refund arrangement again because it's disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2, BlockchainInterface.NULL_ADDRESS)\
            .transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': policy_creator})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, BlockchainInterface.NULL_ADDRESS)\
            .call({'from': policy_creator})

    # But can refund others arrangements
    assert 200 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': policy_creator})
    assert 100 == policy_manager.functions.calculateRefundValue(policy_id_2, node2).call({'from': policy_creator})
    assert 100 == policy_manager.functions.calculateRefundValue(policy_id_2, node3).call({'from': policy_creator})
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 3 * 100 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - 3 * 100 == testerchain.client.get_balance(policy_creator)
    assert policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[2]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node2 == event_args['node']
    assert 100 == event_args['value']

    event_args = events[3]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node3 == event_args['node']
    assert 100 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)
    events = policy_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert 2 * 100 == event_args['value']

    # Create new policy
    period = escrow.functions.getCurrentPeriod().call()
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_3, end_timestamp, [node1])\
        .transact({'from': policy_creator, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    # Mint some periods
    period += 1
    tx = escrow.functions.pushDowntimePeriod(period - 1, period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint(period + 1, 3).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    period += 3
    tx = escrow.functions.setLastActivePeriod(period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 160 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Policy owner revokes policy
    testerchain.time_travel(hours=4)
    assert 40 == policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': policy_creator})
    assert 40 == policy_manager.functions.calculateRefundValue(policy_id_3, node1).call({'from': policy_creator})

    policy_manager_balance = testerchain.client.get_balance(policy_manager.address)
    creator_balance = testerchain.client.get_balance(policy_creator)
    tx = policy_manager.functions.revokePolicy(policy_id_3).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    returned = 40 + 5 * rate
    assert policy_manager_balance - returned == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance + returned == testerchain.client.get_balance(policy_creator)
    assert policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)

    events = arrangement_revoked_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert policy_id_3 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert returned == event_args['value']

    events = policy_revoked_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert policy_id_3 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert returned == event_args['value']

    # Minting is useless after policy is revoked
    tx = escrow.functions.mint(period + 1, 20).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    period += 20
    assert 160 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Create policy again to test double call of `refund` with specific conditions
    policy_id_4 = os.urandom(POLICY_ID_LENGTH)
    number_of_periods_4 = 3
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods_4 - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_4, end_timestamp, [node1]) \
        .transact({'from': policy_creator, 'value': number_of_periods_4 * rate, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=number_of_periods_4 - 2)
    period = escrow.functions.getCurrentPeriod().call()
    creator_balance = testerchain.client.get_balance(policy_creator)
    tx = escrow.functions.pushDowntimePeriod(0, period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(period + 1).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    refund_value = (number_of_periods_4 - 1) * rate
    assert refund_value == policy_manager.functions.calculateRefundValue(policy_id_4).call({'from': policy_creator})

    # Call refund, the result must be almost all ETH without payment for one period
    tx = policy_manager.functions.refund(policy_id_4).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert creator_balance + refund_value == testerchain.client.get_balance(policy_creator)

    events = arrangement_refund_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert policy_id_4 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert refund_value == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert policy_id_4 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert refund_value == event_args['value']

    # Call refund again, the client must not get anything from the second call
    creator_balance = testerchain.client.get_balance(policy_creator)
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_4).call({'from': policy_creator})
    tx = policy_manager.functions.refund(policy_id_4).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert creator_balance == testerchain.client.get_balance(policy_creator)

    events = arrangement_refund_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    assert policy_id_4 == event_args['policyId']
    assert policy_creator == event_args['sender']
    assert node1 == event_args['node']
    assert 0 == event_args['value']

    events = policy_created_log.get_all_entries()
    assert 4 == len(events)


@pytest.mark.slow
def test_reentrancy(testerchain, escrow, policy_manager, deploy_contract):
    withdraw_log = policy_manager.events.Withdrawn.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')

    reentrancy_contract, _ = deploy_contract('ReentrancyTest')
    contract_address = reentrancy_contract.address
    tx = escrow.functions.register(contract_address).transact()
    testerchain.wait_for_receipt(tx)

    # Create policy and mint one period
    policy_value = int(2 * rate)
    transaction = policy_manager.functions.createPolicy(policy_id, 2, 0, [contract_address]) \
        .buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(1, transaction['to'], policy_value, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': contract_address, 'value': 10000})
    testerchain.wait_for_receipt(tx)
    assert policy_value == testerchain.client.get_balance(policy_manager.address)

    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(contract_address, period, 1).transact({'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert rate == policy_manager.functions.nodes(contract_address).call()[REWARD_FIELD]

    # Check protection from reentrancy in withdrawal method
    balance = testerchain.client.get_balance(contract_address)
    transaction = policy_manager.functions.withdraw(contract_address).buildTransaction({'gas': 0})
    # Depth for reentrancy is 2: first initial call and then attempt to call again
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert balance == testerchain.client.get_balance(contract_address)
    assert rate == policy_manager.functions.nodes(contract_address).call()[REWARD_FIELD]
    assert 0 == len(withdraw_log.get_all_entries())

    # Prepare for refund and check reentrancy protection
    tx = escrow.functions.setLastActivePeriod(period).transact()
    testerchain.wait_for_receipt(tx)
    transaction = policy_manager.functions.revokePolicy(policy_id).buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert balance == testerchain.client.get_balance(contract_address)
    assert not policy_manager.functions.policies(policy_id).call()[DISABLED_FIELD]
    assert rate == policy_manager.functions.nodes(contract_address).call()[REWARD_FIELD]
    assert 0 == len(arrangement_revoked_log.get_all_entries())
    assert 0 == len(policy_revoked_log.get_all_entries())
    assert 0 == len(arrangement_refund_log.get_all_entries())
    assert 0 == len(policy_refund_log.get_all_entries())
