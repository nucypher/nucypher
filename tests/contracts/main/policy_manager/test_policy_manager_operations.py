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

from nucypher.blockchain.eth.constants import NULL_ADDRESS, POLICY_ID_LENGTH

DISABLED_FIELD = 0
SPONSOR_FIELD = 1

FEE_FIELD = 0

policy_id = os.urandom(POLICY_ID_LENGTH)
policy_id_2 = os.urandom(POLICY_ID_LENGTH)
policy_id_3 = os.urandom(POLICY_ID_LENGTH)
rate = 20
one_period = 60 * 60
number_of_periods = 10
value = rate * number_of_periods


def test_fee(testerchain, escrow, policy_manager):
    creator, policy_sponsor, bad_node, node1, node2, node3, *everyone_else = testerchain.client.accounts
    node_balance = testerchain.client.get_balance(node1)
    withdraw_log = policy_manager.events.Withdrawn.createFilter(fromBlock='latest')

    # Emulate minting period without policies
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.ping(node1, period - 1, 0, period - 1).transact()
    testerchain.wait_for_receipt(tx)
    assert 0 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]

    for period_to_set_default in range(period, period + number_of_periods + 1):
        tx = escrow.functions.ping(node1, 0, 0, period_to_set_default).transact()
        testerchain.wait_for_receipt(tx)

    # Create policy
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1, node3])\
        .transact({'from': policy_sponsor, 'value': 2 * value})
    testerchain.wait_for_receipt(tx)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.withdraw().transact({'from': node1})
        testerchain.wait_for_receipt(tx)

    # Can't ping directly (only through mint/commitToNextPeriod methods in the escrow contract)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.ping(node1, period - 1, 0, period).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    # Can't register directly (only through deposit method in the escrow contract)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.register(bad_node, period).transact({'from': bad_node})
        testerchain.wait_for_receipt(tx)

    # Mint some periods for calling updateFee method
    for minting_period in range(period - 1, period + 4):
        tx = escrow.functions.ping(node1, minting_period, 0, 0).transact()
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(hours=1)
    period += 4
    assert 80 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]

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
    tx = escrow.functions.ping(node1, 0, 0, period).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.ping(node1, 0, 0, period + 1).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.ping(node1, 0, 0, period + 2).transact()
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=2)
    tx = escrow.functions.ping(node1, period, period + 1, period + 3).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.ping(node1, period + 2, 0, period + 4).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.ping(node1, 0, period + 3, period + 5).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    tx = escrow.functions.ping(node1, period + 4, period + 5, 0).transact()
    testerchain.wait_for_receipt(tx)

    period += 6
    assert 120 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]
    testerchain.time_travel(hours=1)
    tx = escrow.functions.ping(node1, period, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 120 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]

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
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.ping(node1, 0, 0, period).transact()
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_2, policy_sponsor, end_timestamp, [node2, node3]) \
        .transact({'from': policy_sponsor, 'value': int(2 * value)})
    testerchain.wait_for_receipt(tx)

    # Mint some periods
    for minting_period in range(period, period + 5):
        testerchain.time_travel(hours=1)
        tx = escrow.functions.ping(node2, 0, minting_period, 0).transact()
        testerchain.wait_for_receipt(tx)
    period += 5
    assert 100 == policy_manager.functions.nodes(node2).call()[FEE_FIELD]

    # Mint more periods
    for minting_period in range(period, period + 6):
        testerchain.time_travel(hours=1)
        tx = escrow.functions.ping(node2, 0, minting_period, 0).transact()
        testerchain.wait_for_receipt(tx)
    period += 6
    assert 200 == policy_manager.functions.nodes(node2).call()[FEE_FIELD]

    # Withdraw the second node fee to the first node
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


def test_refund(testerchain, escrow, policy_manager):
    creator, policy_creator, bad_node, node1, node2, node3, policy_owner, *everyone_else = testerchain.client.accounts

    creator_balance = testerchain.client.get_balance(policy_creator)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')

    # Create policy
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id, policy_owner, end_timestamp, [node1]) \
        .transact({'from': policy_creator, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.setLastCommittedPeriod(period - 1).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=8)
    # Check that methods only calculate value
    tx = policy_manager.functions.calculateRefundValue(policy_id).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.calculateRefundValue(policy_id, node1).transact({'from': policy_owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 200 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - 200 == testerchain.client.get_balance(policy_creator)
    assert 180 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': policy_creator})
    assert 180 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': policy_owner})

    # Call refund, the result must be almost all ETH without payment for one period
    tx = policy_manager.functions.refund(policy_id).transact({'from': policy_creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 20 == testerchain.client.get_balance(policy_manager.address)
    assert creator_balance - 20 == testerchain.client.get_balance(policy_creator)
    assert policy_creator == policy_manager.functions.policies(policy_id).call()[SPONSOR_FIELD]

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
    tx = policy_manager.functions.refund(policy_id).transact({'from': policy_owner, 'gas_price': 0})
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
    assert policy_owner == event_args['sender']
    assert node1 == event_args['node']
    assert 20 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 1 == len(events)
    events = policy_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_owner == event_args['sender']
    assert 20 == event_args['value']

    # Can't refund again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, node1).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, NULL_ADDRESS).transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id).call({'from': policy_creator})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': policy_creator})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, NULL_ADDRESS).call({'from': policy_creator})

    # Create new policy
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.setLastCommittedPeriod(period).transact()
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_2, policy_creator, end_timestamp, [node1, node2, node3]) \
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
    # Only policy creator or owner can call refund
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': node1})

    # Mint some periods and mark others as downtime periods
    testerchain.time_travel(hours=1)
    tx = escrow.functions.ping(node1, 0, period, 0).transact()
    testerchain.wait_for_receipt(tx)
    period += 1
    testerchain.time_travel(hours=2)
    tx = escrow.functions.ping(node1, period, period + 1, 0).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    tx = escrow.functions.pushDowntimePeriod(period + 2, period + 3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.ping(node1, period + 4, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    tx = escrow.functions.pushDowntimePeriod(period + 5, period + 7).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.ping(node1, period + 8, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setLastCommittedPeriod(period + 8).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 100 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]

    testerchain.time_travel(hours=1)
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
        tx = policy_manager.functions.refund(policy_id_2, NULL_ADDRESS)\
            .transact({'from': policy_creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': policy_creator})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, NULL_ADDRESS)\
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
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_3, policy_creator, end_timestamp, [node1])\
        .transact({'from': policy_creator, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    # Mint some periods
    period += 1
    tx = escrow.functions.pushDowntimePeriod(period - 1, period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    tx = escrow.functions.ping(node1, period + 1, period + 2, 0).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    tx = escrow.functions.ping(node1, period + 3, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    period += 3
    tx = escrow.functions.setLastCommittedPeriod(period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 160 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]

    # Policy owner revokes policy
    assert 40 == policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': policy_creator})
    assert 40 == policy_manager.functions.calculateRefundValue(policy_id_3, node1).call({'from': policy_creator})

    policy_manager_balance = testerchain.client.get_balance(policy_manager.address)
    creator_balance = testerchain.client.get_balance(policy_creator)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    for period_to_set_default in range(period + 1, period + number_of_periods):
        tx = escrow.functions.ping(node1, 0, 0, period_to_set_default).transact()
        testerchain.wait_for_receipt(tx)
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
    for minting_period in range(period + 1, period + number_of_periods + 1):
        testerchain.time_travel(hours=1)
        tx = escrow.functions.ping(node1, 0, minting_period, 0).transact()
        testerchain.wait_for_receipt(tx)
    period += 20
    assert 160 == policy_manager.functions.nodes(node1).call()[FEE_FIELD]

    # Create policy again to test double call of `refund` with specific conditions
    testerchain.time_travel(hours=number_of_periods + 2)
    policy_id_4 = os.urandom(POLICY_ID_LENGTH)
    number_of_periods_4 = 3
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods_4 - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_4, policy_creator, end_timestamp, [node1]) \
        .transact({'from': policy_creator, 'value': number_of_periods_4 * rate, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=number_of_periods_4 - 2)
    period = escrow.functions.getCurrentPeriod().call()
    creator_balance = testerchain.client.get_balance(policy_creator)
    tx = escrow.functions.pushDowntimePeriod(0, period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setLastCommittedPeriod(period + 1).transact({'from': creator})
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
    periods = 3
    policy_value = int(periods * rate)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (periods - 1) * one_period
    transaction = policy_manager.functions.createPolicy(policy_id, contract_address, end_timestamp, [contract_address])\
        .buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(1, transaction['to'], policy_value, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': contract_address, 'value': 10000})
    testerchain.wait_for_receipt(tx)
    assert policy_value == testerchain.client.get_balance(policy_manager.address)

    tx = policy_manager.functions.createPolicy(
        policy_id_2, NULL_ADDRESS, end_timestamp, [contract_address])\
        .transact({'value': policy_value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.ping(contract_address, 0, period, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 2 * rate == policy_manager.functions.nodes(contract_address).call()[FEE_FIELD]

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
    assert 2 * rate == policy_manager.functions.nodes(contract_address).call()[FEE_FIELD]
    assert 0 == len(withdraw_log.get_all_entries())

    # Prepare for refund and check reentrancy protection
    tx = escrow.functions.setLastCommittedPeriod(period).transact()
    testerchain.wait_for_receipt(tx)
    transaction = policy_manager.functions.revokePolicy(policy_id).buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert balance == testerchain.client.get_balance(contract_address)
    assert not policy_manager.functions.policies(policy_id).call()[DISABLED_FIELD]
    assert 2 * rate == policy_manager.functions.nodes(contract_address).call()[FEE_FIELD]
    assert 0 == len(arrangement_revoked_log.get_all_entries())
    assert 0 == len(policy_revoked_log.get_all_entries())
    assert 0 == len(arrangement_refund_log.get_all_entries())
    assert 0 == len(policy_refund_log.get_all_entries())


def test_revoke_and_default_state(testerchain, escrow, policy_manager):
    creator, policy_sponsor, bad_node, node1, node2, node3, *everyone_else = testerchain.client.accounts

    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + one_period
    current_period = policy_manager.functions.getCurrentPeriod().call()
    target_period = current_period + 2

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1])\
        .transact({'from': policy_sponsor, 'value': 2 * rate, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.getNodeFeeDelta(node1, target_period).call() == -rate

    testerchain.time_travel(hours=2)
    current_period = policy_manager.functions.getCurrentPeriod().call()
    assert current_period == target_period

    # Create new policy where start is the target period (current)
    assert policy_manager.functions.getNodeFeeDelta(node1, current_period).call() == -rate
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + one_period
    tx = policy_manager.functions.createPolicy(policy_id_2, policy_sponsor, end_timestamp, [node1])\
        .transact({'from': policy_sponsor, 'value': 4 * rate, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.getNodeFeeDelta(node1, current_period).call() == rate

    # Revoke first policy
    tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': policy_sponsor, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.getNodeFeeDelta(node1, current_period).call() == rate
