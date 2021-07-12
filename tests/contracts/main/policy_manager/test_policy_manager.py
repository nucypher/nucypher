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
from eth_utils import to_canonical_address
from web3.contract import Contract

from nucypher.blockchain.eth.constants import NULL_ADDRESS, POLICY_ID_LENGTH

DISABLED_FIELD = 0
SPONSOR_FIELD = 1
OWNER_FIELD = 2
RATE_FIELD = 3
START_TIMESTAMP_FIELD = 4
END_TIMESTAMP_FIELD = 5

FEE_FIELD = 0
PREVIOUS_FEE_PERIOD_FIELD = 1
FEE_RATE_FIELD = 2
MIN_FEE_RATE_FIELD = 3


def test_create_revoke(testerchain, escrow, policy_manager):
    creator, policy_sponsor, bad_node, node1, node2, node3, policy_owner, *everyone_else = testerchain.client.accounts

    rate = 20
    one_period = 60 * 60
    number_of_periods = 10
    value = rate * number_of_periods

    policy_sponsor_balance = testerchain.client.get_balance(policy_sponsor)
    policy_owner_balance = testerchain.client.get_balance(policy_owner)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')
    min_fee_log = policy_manager.events.MinFeeRateSet.createFilter(fromBlock='latest')
    fee_range_log = policy_manager.events.FeeRateRangeSet.createFilter(fromBlock='latest')

    # Only past periods is allowed in register method
    current_period = policy_manager.functions.getCurrentPeriod().call()
    node_for_registering = everyone_else[0]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.register(node_for_registering, current_period).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.register(node_for_registering, current_period + 1).transact()
        testerchain.wait_for_receipt(tx)

    tx = escrow.functions.register(node_for_registering, current_period - 1).transact()
    testerchain.wait_for_receipt(tx)
    assert 0 < policy_manager.functions.nodes(node_for_registering).call()[PREVIOUS_FEE_PERIOD_FIELD]

    # Can't register twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.register(node_for_registering, current_period - 2).transact()
        testerchain.wait_for_receipt(tx)

    # Check registered nodes
    assert 0 < policy_manager.functions.nodes(node1).call()[PREVIOUS_FEE_PERIOD_FIELD]
    assert 0 < policy_manager.functions.nodes(node2).call()[PREVIOUS_FEE_PERIOD_FIELD]
    assert 0 < policy_manager.functions.nodes(node3).call()[PREVIOUS_FEE_PERIOD_FIELD]
    assert 0 == policy_manager.functions.nodes(bad_node).call()[PREVIOUS_FEE_PERIOD_FIELD]
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    policy_id = os.urandom(POLICY_ID_LENGTH)

    # Try to create policy for bad (unregistered) node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [bad_node])\
            .transact({'from': policy_sponsor, 'value': value})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1, bad_node])\
            .transact({'from': policy_sponsor, 'value': value})
        testerchain.wait_for_receipt(tx)

    # Try to create policy with no ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)

    # Can't create policy using timestamp from the past
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, current_timestamp -1, [node1])\
            .transact({'from': policy_sponsor, 'value': value})
        testerchain.wait_for_receipt(tx)

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1])\
        .transact({'from': policy_sponsor, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    # Check balances and policy info
    assert value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 200 == testerchain.client.get_balance(policy_sponsor)
    policy = policy_manager.functions.policies(policy_id).call()
    assert policy_sponsor == policy[SPONSOR_FIELD]
    assert NULL_ADDRESS == policy[OWNER_FIELD]
    assert rate == policy[RATE_FIELD]
    assert current_timestamp == policy[START_TIMESTAMP_FIELD]
    assert end_timestamp == policy[END_TIMESTAMP_FIELD]
    assert not policy[DISABLED_FIELD]
    assert 1 == policy_manager.functions.getArrangementsLength(policy_id).call()
    assert node1 == policy_manager.functions.getArrangementInfo(policy_id, 0).call()[0]
    assert policy_sponsor == policy_manager.functions.getPolicyOwner(policy_id).call()

    events = policy_created_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_sponsor == event_args['sponsor']
    assert policy_sponsor == event_args['owner']
    assert rate == event_args['feeRate']
    assert current_timestamp == event_args['startTimestamp']
    assert end_timestamp == event_args['endTimestamp']
    assert 1 == event_args['numberOfNodes']

    # Can't create policy with the same id
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': value})
        testerchain.wait_for_receipt(tx)

    # Only policy owner can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': policy_sponsor, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.policies(policy_id).call()[DISABLED_FIELD]

    events = policy_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_sponsor == event_args['sender']
    assert value == event_args['value']
    events = arrangement_revoked_log.get_all_entries()
    assert 1 == len(events)

    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert policy_sponsor == event_args['sender']
    assert node1 == event_args['node']
    assert value == event_args['value']

    # Can't revoke again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id, node1).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)
    # Can't create policy with the same id even after revoking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': value})
        testerchain.wait_for_receipt(tx)

    # Create new policy
    period = escrow.functions.getCurrentPeriod().call()
    for period_to_set_default in range(period, period + number_of_periods + 1):
        tx = escrow.functions.ping(node1, 0, 0, period_to_set_default).transact()
        testerchain.wait_for_receipt(tx)
    for period_to_set_default in range(period, period + number_of_periods + 1):
        tx = escrow.functions.ping(node2, 0, 0, period_to_set_default).transact()
        testerchain.wait_for_receipt(tx)
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    policy_id_2 = os.urandom(POLICY_ID_LENGTH)
    tx = policy_manager.functions.createPolicy(policy_id_2, policy_owner, end_timestamp, [node1, node2, node3])\
        .transact({'from': policy_sponsor, 'value': 6 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert 6 * value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 6 * value == testerchain.client.get_balance(policy_sponsor)
    policy = policy_manager.functions.policies(policy_id_2).call()
    assert policy_sponsor == policy[SPONSOR_FIELD]
    assert policy_owner == policy[OWNER_FIELD]
    assert 2 * rate == policy[RATE_FIELD]
    assert current_timestamp == policy[START_TIMESTAMP_FIELD]
    assert end_timestamp == policy[END_TIMESTAMP_FIELD]
    assert not policy[DISABLED_FIELD]
    assert policy_owner == policy_manager.functions.getPolicyOwner(policy_id_2).call()

    events = policy_created_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_sponsor == event_args['sponsor']
    assert policy_owner == event_args['owner']
    assert 2 * rate == event_args['feeRate']
    assert current_timestamp == event_args['startTimestamp']
    assert end_timestamp == event_args['endTimestamp']
    assert 3 == event_args['numberOfNodes']

    # Can't revoke nonexistent arrangement
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, testerchain.client.accounts[6])\
            .transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)
    # Can't revoke null arrangement (also it's nonexistent)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, NULL_ADDRESS).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)

    # Policy sponsor can't revoke policy, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)

    # Revoke only one arrangement
    tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': policy_owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 4 * value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 4 * value == testerchain.client.get_balance(policy_sponsor)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]
    assert policy_owner_balance == testerchain.client.get_balance(policy_owner)

    events = arrangement_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_owner == event_args['sender']
    assert node1 == event_args['node']
    assert 2 * value == event_args['value']

    # Can't revoke again because arrangement is disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)
    # Can't revoke null arrangement (it's nonexistent)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, NULL_ADDRESS).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)

    # Revoke policy with remaining arrangements
    tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': policy_owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance == testerchain.client.get_balance(policy_sponsor)
    assert policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[2]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_owner == event_args['sender']
    assert node2 == event_args['node']
    assert 2 * value == event_args['value']

    event_args = events[3]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_owner == event_args['sender']
    assert node3 == event_args['node']
    assert 2 * value == event_args['value']
    events = policy_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert policy_owner == event_args['sender']
    assert 4 * value == event_args['value']

    # Can't revoke policy again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)

    # Can't create policy with wrong ETH value - when fee is not calculated by formula:
    # numberOfNodes * feeRate * numberOfPeriods
    policy_id_3 = os.urandom(POLICY_ID_LENGTH)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': 11})
        testerchain.wait_for_receipt(tx)

    # Can't set minimum fee because range is [0, 0]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.setMinFeeRate(10).transact({'from': node1})
        testerchain.wait_for_receipt(tx)

    # Only owner can change range
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.setFeeRateRange(10, 20, 30).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.feeRateRange().call() == [0, 0, 0]

    tx = policy_manager.functions.setMinFeeRate(0).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.getMinFeeRate(node1).call() == 0
    assert len(min_fee_log.get_all_entries()) == 0

    tx = policy_manager.functions.setFeeRateRange(0, 0, 0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.feeRateRange().call() == [0, 0, 0]

    events = fee_range_log.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == creator
    assert event_args['min'] == 0
    assert event_args['defaultValue'] == 0
    assert event_args['max'] == 0

    # Can't set range with inconsistent values
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.setFeeRateRange(10, 5, 11).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.setFeeRateRange(10, 15, 11).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    min_rate, default_rate, max_rate = 10, 20, 30
    tx = policy_manager.functions.setFeeRateRange(min_rate, default_rate, max_rate).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.feeRateRange().call() == [min_rate, default_rate, max_rate]
    assert policy_manager.functions.nodes(node1).call()[MIN_FEE_RATE_FIELD] == 0
    assert policy_manager.functions.nodes(node2).call()[MIN_FEE_RATE_FIELD] == 0
    assert policy_manager.functions.getMinFeeRate(node1).call() == default_rate
    assert policy_manager.functions.getMinFeeRate(node2).call() == default_rate

    events = fee_range_log.get_all_entries()
    assert len(events) == 2
    event_args = events[1]['args']
    assert event_args['sender'] == creator
    assert event_args['min'] == min_rate
    assert event_args['defaultValue'] == default_rate
    assert event_args['max'] == max_rate

    # Can't set min fee let out of range
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.setMinFeeRate(5).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.setMinFeeRate(35).transact({'from': node1})
        testerchain.wait_for_receipt(tx)

    # Set minimum fee rate for nodes
    tx = policy_manager.functions.setMinFeeRate(10).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.setMinFeeRate(20).transact({'from': node2})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.nodes(node1).call()[MIN_FEE_RATE_FIELD] == 10
    assert policy_manager.functions.nodes(node2).call()[MIN_FEE_RATE_FIELD] == 20
    assert policy_manager.functions.getMinFeeRate(node1).call() == 10
    assert policy_manager.functions.getMinFeeRate(node2).call() == 20

    events = min_fee_log.get_all_entries()
    assert len(events) == 2
    event_args = events[0]['args']
    assert event_args['node'] == node1
    assert event_args['value'] == 10
    event_args = events[1]['args']
    assert event_args['node'] == node2
    assert event_args['value'] == 20

    # Try to create policy with low rate
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + 10
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': 5})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, policy_sponsor, end_timestamp, [node1, node2])\
            .transact({'from': policy_sponsor, 'value': 30})
        testerchain.wait_for_receipt(tx)

    # Create new policy
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(
        policy_id_3, NULL_ADDRESS, end_timestamp, [node1, node2]) \
        .transact({'from': policy_sponsor, 'value': 2 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert 2 * value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 2 * value == testerchain.client.get_balance(policy_sponsor)
    policy = policy_manager.functions.policies(policy_id_3).call()
    assert policy_sponsor == policy[SPONSOR_FIELD]
    assert NULL_ADDRESS == policy[OWNER_FIELD]
    assert rate == policy[RATE_FIELD]
    assert current_timestamp == policy[START_TIMESTAMP_FIELD]
    assert end_timestamp == policy[END_TIMESTAMP_FIELD]
    assert not policy[DISABLED_FIELD]
    assert policy_sponsor == policy_manager.functions.getPolicyOwner(policy_id_3).call()

    events = policy_created_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert policy_id_3 == event_args['policyId']
    assert policy_sponsor == event_args['sponsor']
    assert policy_sponsor == event_args['owner']
    assert rate == event_args['feeRate']
    assert current_timestamp == event_args['startTimestamp']
    assert end_timestamp == event_args['endTimestamp']
    assert 2 == event_args['numberOfNodes']

    # Revocation using signature

    data = policy_id_3 + to_canonical_address(node1)
    wrong_signature = testerchain.client.sign_message(account=creator, message=data)
    # Only owner's signature can be used
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revoke(policy_id_3, node1, wrong_signature)\
            .transact({'from': policy_sponsor, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    signature = testerchain.client.sign_message(account=policy_sponsor, message=data)
    tx = policy_manager.functions.revoke(policy_id_3, node1, signature)\
        .transact({'from': policy_sponsor, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - value == testerchain.client.get_balance(policy_sponsor)
    assert not policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]
    assert NULL_ADDRESS == policy_manager.functions.getArrangementInfo(policy_id_3, 0).call()[0]
    assert node2 == policy_manager.functions.getArrangementInfo(policy_id_3, 1).call()[0]

    data = policy_id_3 + to_canonical_address(NULL_ADDRESS)
    signature = testerchain.client.sign_message(account=policy_sponsor, message=data)
    tx = policy_manager.functions.revoke(policy_id_3, NULL_ADDRESS, signature)\
        .transact({'from': creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]

    # Create new policy
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    policy_id_4 = os.urandom(POLICY_ID_LENGTH)
    tx = policy_manager.functions.createPolicy(policy_id_4, policy_owner, end_timestamp, [node1, node2, node3]) \
        .transact({'from': policy_sponsor, 'value': 3 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    data = policy_id_4 + to_canonical_address(NULL_ADDRESS)
    wrong_signature = testerchain.client.sign_message(account=policy_sponsor, message=data)
    # Only owner's signature can be used
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revoke(policy_id_4, NULL_ADDRESS, wrong_signature)\
            .transact({'from': policy_owner, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    signature = testerchain.client.sign_message(account=policy_owner, message=data)
    tx = policy_manager.functions.revoke(policy_id_4, NULL_ADDRESS, signature)\
        .transact({'from': creator, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.policies(policy_id_4).call()[DISABLED_FIELD]

    events = policy_revoked_log.get_all_entries()
    assert 4 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 9 == len(events)

    events = arrangement_refund_log.get_all_entries()
    assert 0 == len(events)
    events = policy_refund_log.get_all_entries()
    assert 0 == len(events)

    # If min fee rate is outside of the range after changing it - then default value must be returned
    min_rate, default_rate, max_rate = 11, 15, 19
    tx = policy_manager.functions.setFeeRateRange(min_rate, default_rate, max_rate).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.feeRateRange().call() == [min_rate, default_rate, max_rate]
    assert policy_manager.functions.nodes(node1).call()[MIN_FEE_RATE_FIELD] == 10
    assert policy_manager.functions.nodes(node2).call()[MIN_FEE_RATE_FIELD] == 20
    assert policy_manager.functions.getMinFeeRate(node1).call() == default_rate
    assert policy_manager.functions.getMinFeeRate(node2).call() == default_rate

    events = fee_range_log.get_all_entries()
    assert len(events) == 3
    event_args = events[2]['args']
    assert event_args['sender'] == creator
    assert event_args['min'] == min_rate
    assert event_args['defaultValue'] == default_rate
    assert event_args['max'] == max_rate

    # Try to create policy with low rate
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + 10
    policy_id_5 = os.urandom(POLICY_ID_LENGTH)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions\
            .createPolicy(policy_id_5, NULL_ADDRESS, end_timestamp, [node1]) \
            .transact({'from': policy_sponsor, 'value': default_rate - 1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions\
            .createPolicy(policy_id_5, NULL_ADDRESS, end_timestamp, [node2]) \
            .transact({'from': policy_sponsor, 'value': default_rate - 1})
        testerchain.wait_for_receipt(tx)

    tx = policy_manager.functions \
        .createPolicy(policy_id_5, NULL_ADDRESS, end_timestamp, [node1, node2]) \
        .transact({'from': policy_sponsor, 'value': 2 * default_rate})
    testerchain.wait_for_receipt(tx)


def test_create_multiple_policies(testerchain, escrow, policy_manager):
    creator, policy_sponsor, bad_node, node1, node2, node3, policy_owner, *everyone_else = testerchain.client.accounts

    rate = 20
    one_period = 60 * 60
    number_of_periods = 10
    value = rate * number_of_periods
    default_fee_delta = policy_manager.functions.DEFAULT_FEE_DELTA().call()

    policy_sponsor_balance = testerchain.client.get_balance(policy_sponsor)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')

    # Check registered nodes
    assert 0 < policy_manager.functions.nodes(node1).call()[PREVIOUS_FEE_PERIOD_FIELD]
    assert 0 < policy_manager.functions.nodes(node2).call()[PREVIOUS_FEE_PERIOD_FIELD]
    assert 0 < policy_manager.functions.nodes(node3).call()[PREVIOUS_FEE_PERIOD_FIELD]
    assert 0 == policy_manager.functions.nodes(bad_node).call()[PREVIOUS_FEE_PERIOD_FIELD]
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period

    policy_id_1 = os.urandom(POLICY_ID_LENGTH)
    policy_id_2 = os.urandom(POLICY_ID_LENGTH)
    policies = [policy_id_1, policy_id_2]

    # Try to create policy for bad (unregistered) node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [bad_node])\
            .transact({'from': policy_sponsor, 'value': 2 * value})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [node1, bad_node])\
            .transact({'from': policy_sponsor, 'value': 2 * value})
        testerchain.wait_for_receipt(tx)

    # Try to create policy with no ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor})
        testerchain.wait_for_receipt(tx)

    # Can't create policy using timestamp from the past
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, current_timestamp - 1, [node1])\
            .transact({'from': policy_sponsor, 'value': 2 * value})
        testerchain.wait_for_receipt(tx)

    # Can't create two policies with the same id
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies([policy_id_1, policy_id_1], policy_sponsor, end_timestamp, [node1]) \
            .transact({'from': policy_sponsor, 'value': 2 * value, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Can't use createPolicies() method for only one policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies([policy_id_1], policy_sponsor, end_timestamp, [node1]) \
            .transact({'from': policy_sponsor, 'value': value, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Create policy
    current_period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [node1])\
        .transact({'from': policy_sponsor, 'value': 2 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    # Check balances and policy info
    assert 2 * value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 2 * value == testerchain.client.get_balance(policy_sponsor)

    events = policy_created_log.get_all_entries()
    assert len(events) == 2

    for i, policy_id in enumerate(policies):
        policy = policy_manager.functions.policies(policy_id).call()
        assert policy_sponsor == policy[SPONSOR_FIELD]
        assert NULL_ADDRESS == policy[OWNER_FIELD]
        assert rate == policy[RATE_FIELD]
        assert current_timestamp == policy[START_TIMESTAMP_FIELD]
        assert end_timestamp == policy[END_TIMESTAMP_FIELD]
        assert not policy[DISABLED_FIELD]
        assert 1 == policy_manager.functions.getArrangementsLength(policy_id).call()
        assert node1 == policy_manager.functions.getArrangementInfo(policy_id, 0).call()[0]
        assert policy_sponsor == policy_manager.functions.getPolicyOwner(policy_id).call()
        assert policy_manager.functions.getNodeFeeDelta(node1, current_period).call() == 2 * rate
        assert policy_manager.functions.getNodeFeeDelta(node1, current_period + number_of_periods).call() == -2 * rate

        event_args = events[i]['args']
        assert policy_id == event_args['policyId']
        assert policy_sponsor == event_args['sponsor']
        assert policy_sponsor == event_args['owner']
        assert rate == event_args['feeRate']
        assert current_timestamp == event_args['startTimestamp']
        assert end_timestamp == event_args['endTimestamp']
        assert 1 == event_args['numberOfNodes']

    # Can't create policy with the same id
    policy_id_3 = os.urandom(POLICY_ID_LENGTH)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies([policy_id_3, policy_id_1], policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': 2 * value})
        testerchain.wait_for_receipt(tx)

    # Revoke policies
    tx = policy_manager.functions.revokePolicy(policy_id_1).transact({'from': policy_sponsor, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': policy_sponsor, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.policies(policy_id_1).call()[DISABLED_FIELD]
    assert policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    # Create new policy
    testerchain.time_travel(hours=1)
    current_period = escrow.functions.getCurrentPeriod().call()
    for period_to_set_default in range(current_period, current_period + number_of_periods + 1):
        tx = escrow.functions.ping(node1, 0, 0, period_to_set_default).transact()
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.ping(node2, 0, 0, period_to_set_default).transact()
        testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    policy_id_1 = os.urandom(POLICY_ID_LENGTH)
    policy_id_2 = os.urandom(POLICY_ID_LENGTH)
    policies = [policy_id_1, policy_id_2]
    tx = policy_manager.functions.createPolicies(policies, policy_owner, end_timestamp, [node1, node2, node3])\
        .transact({'from': policy_sponsor, 'value': 6 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert 6 * value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 6 * value == testerchain.client.get_balance(policy_sponsor)
    events = policy_created_log.get_all_entries()
    assert len(events) == 4

    for i, policy_id in enumerate(policies):
        policy = policy_manager.functions.policies(policy_id).call()
        assert policy_sponsor == policy[SPONSOR_FIELD]
        assert policy_owner == policy[OWNER_FIELD]
        assert rate == policy[RATE_FIELD]
        assert current_timestamp == policy[START_TIMESTAMP_FIELD]
        assert end_timestamp == policy[END_TIMESTAMP_FIELD]
        assert not policy[DISABLED_FIELD]
        assert policy_owner == policy_manager.functions.getPolicyOwner(policy_id).call()
        assert policy_manager.functions.getNodeFeeDelta(node1, current_period).call() == default_fee_delta
        assert policy_manager.functions.getNodeFeeDelta(node1, current_period + number_of_periods).call() == -2 * rate
        assert policy_manager.functions.getNodeFeeDelta(node2, current_period).call() == 2 * rate
        assert policy_manager.functions.getNodeFeeDelta(node2, current_period + number_of_periods).call() == -2 * rate
        assert policy_manager.functions.getNodeFeeDelta(node3, current_period).call() == 2 * rate
        assert policy_manager.functions.getNodeFeeDelta(node3, current_period + number_of_periods).call() == -2 * rate

        event_args = events[i + 2]['args']
        assert policy_id == event_args['policyId']
        assert policy_sponsor == event_args['sponsor']
        assert policy_owner == event_args['owner']
        assert rate == event_args['feeRate']
        assert current_timestamp == event_args['startTimestamp']
        assert end_timestamp == event_args['endTimestamp']
        assert 3 == event_args['numberOfNodes']

    # Revoke policies
    tx = policy_manager.functions.revokePolicy(policy_id_1).transact({'from': policy_owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': policy_owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.policies(policy_id_1).call()[DISABLED_FIELD]
    assert policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    # Can't create policy with wrong ETH value - when fee is not calculated by formula:
    # numberOfNodes * feeRate * numberOfPeriods * numberOfPolicies
    policy_id_1 = os.urandom(POLICY_ID_LENGTH)
    policy_id_2 = os.urandom(POLICY_ID_LENGTH)
    policies = [policy_id_1, policy_id_2]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': value - 1})
        testerchain.wait_for_receipt(tx)

    min_rate, default_rate, max_rate = 10, 20, 30
    tx = policy_manager.functions.setFeeRateRange(min_rate, default_rate, max_rate).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Set minimum fee rate for nodes
    tx = policy_manager.functions.setMinFeeRate(10).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.setMinFeeRate(20).transact({'from': node2})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.nodes(node1).call()[MIN_FEE_RATE_FIELD] == 10
    assert policy_manager.functions.nodes(node2).call()[MIN_FEE_RATE_FIELD] == 20
    assert policy_manager.functions.getMinFeeRate(node1).call() == 10
    assert policy_manager.functions.getMinFeeRate(node2).call() == 20

    # Try to create policy with low rate
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    end_timestamp = current_timestamp + 10
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [node1])\
            .transact({'from': policy_sponsor, 'value': 2 * (min_rate - 1)})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicies(policies, policy_sponsor, end_timestamp, [node1, node2])\
            .transact({'from': policy_sponsor, 'value': 2 * 2 * (min_rate + 1)})
        testerchain.wait_for_receipt(tx)

    # Create new policy
    value = 2 * default_rate * number_of_periods
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicies(
        policies, NULL_ADDRESS, end_timestamp, [node1, node2]) \
        .transact({'from': policy_sponsor, 'value': 2 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    current_timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert 2 * value == testerchain.client.get_balance(policy_manager.address)
    assert policy_sponsor_balance - 2 * value == testerchain.client.get_balance(policy_sponsor)
    events = policy_created_log.get_all_entries()
    assert len(events) == 6

    for i, policy_id in enumerate(policies):
        policy = policy_manager.functions.policies(policy_id).call()
        assert policy_sponsor == policy[SPONSOR_FIELD]
        assert NULL_ADDRESS == policy[OWNER_FIELD]
        assert default_rate == policy[RATE_FIELD]
        assert current_timestamp == policy[START_TIMESTAMP_FIELD]
        assert end_timestamp == policy[END_TIMESTAMP_FIELD]
        assert not policy[DISABLED_FIELD]
        assert policy_sponsor == policy_manager.functions.getPolicyOwner(policy_id).call()

        event_args = events[i + 4]['args']
        assert policy_id == event_args['policyId']
        assert policy_sponsor == event_args['sponsor']
        assert policy_sponsor == event_args['owner']
        assert rate == event_args['feeRate']
        assert current_timestamp == event_args['startTimestamp']
        assert end_timestamp == event_args['endTimestamp']
        assert 2 == event_args['numberOfNodes']


def test_upgrading(testerchain, deploy_contract):
    creator = testerchain.client.accounts[0]

    # Deploy contracts
    escrow1, _ = deploy_contract('StakingEscrowForPolicyMock', 1, 1)
    escrow2, _ = deploy_contract('StakingEscrowForPolicyMock', 1, 1)
    address1 = escrow1.address
    address2 = escrow2.address

    # Only escrow contract is allowed in PolicyManager constructor
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('PolicyManager', creator, address1)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('PolicyManager', address1, creator)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('PolicyManager', creator, creator)

    contract_library_v1, _ = deploy_contract('ExtendedPolicyManager', address1)
    dispatcher, _ = deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = deploy_contract('PolicyManagerV2Mock', address2)
    contract = testerchain.client.get_contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    tx = contract.functions.setFeeRateRange(10, 15, 20).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Upgrade to the second version
    assert address1 == contract.functions.escrow().call()
    tx = dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check constructor and storage values
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert address2 == contract.functions.escrow().call()
    # Check new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = deploy_contract('PolicyManagerBad', address2)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert address1 == contract.functions.escrow().call()
    # After rollback new ABI is unavailable
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    events = dispatcher.events.StateVerified.createFilter(fromBlock=0).get_all_entries()
    assert 4 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['testTarget']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[2]['args']
    event_args = events[3]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0).get_all_entries()
    assert 3 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[2]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']


def test_handling_wrong_state(testerchain, deploy_contract):
    creator, node1, node2, *everyone_else = testerchain.client.accounts

    # Prepare enhanced version of contract
    escrow, _ = deploy_contract('StakingEscrowForPolicyMock', 1, 1)
    policy_manager, _ = deploy_contract('ExtendedPolicyManager', escrow.address)
    tx = escrow.functions.setPolicyManager(policy_manager.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    current_period = policy_manager.functions.getCurrentPeriod().call()
    initial_period = current_period - 1
    tx = escrow.functions.register(node1, initial_period).transact()
    testerchain.wait_for_receipt(tx)

    # Prepare broken state, emulates creating policy in the same period as node was registered
    number_of_periods = 2
    tx = policy_manager.functions.setNodeFeeDelta(node1, initial_period, 1).transact()
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.setNodeFeeDelta(node1, initial_period + number_of_periods, -1).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.ping(node1, 0, 0, current_period).transact()
    testerchain.wait_for_receipt(tx)

    # Emulate making a commitments
    testerchain.time_travel(hours=1)
    current_period = policy_manager.functions.getCurrentPeriod().call()
    tx = escrow.functions.ping(node1, 0, current_period - 1, current_period + 1).transact()
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    current_period = policy_manager.functions.getCurrentPeriod().call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.ping(node1, 0, current_period - 1, current_period + 1).transact()
        testerchain.wait_for_receipt(tx)
