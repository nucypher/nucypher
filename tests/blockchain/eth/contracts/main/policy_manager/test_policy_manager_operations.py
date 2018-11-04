"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

import pytest
from eth_tester.exceptions import TransactionFailed

NULL_ADDR = '0x' + '0' * 40

CLIENT_FIELD = 0
RATE_FIELD = 1
FIRST_REWARD_FIELD = 2
START_PERIOD_FIELD = 3
LAST_PERIOD_FIELD = 4
DISABLED_FIELD = 5

REWARD_FIELD = 0
REWARD_RATE_FIELD = 1
LAST_MINED_PERIOD_FIELD = 2
MIN_REWARD_RATE_FIELD = 3

POLICY_ID_LENGTH = 16
policy_id = os.urandom(POLICY_ID_LENGTH)
policy_id_2 = os.urandom(POLICY_ID_LENGTH)
policy_id_3 = os.urandom(POLICY_ID_LENGTH)
rate = 20
number_of_periods = 10
value = rate * number_of_periods


@pytest.mark.slow
def test_reward(testerchain, escrow, policy_manager):
    creator, client, bad_node, node1, node2, node3, *everyone_else = testerchain.interface.w3.eth.accounts
    node_balance = testerchain.interface.w3.eth.getBalance(node1)
    withdraw_log = policy_manager.events.Withdrawn.createFilter(fromBlock='latest')

    # Mint period without policies
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, 0, [node1, node3])\
        .transact({'from': client, 'value': 2 * value})
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
    tx = escrow.functions.mint(period, 5).transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period += 5
    assert 80 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Withdraw some ETH
    tx = policy_manager.functions.withdraw().transact({'from': node1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert node_balance + 80 == testerchain.interface.w3.eth.getBalance(node1)
    assert 120 + value == testerchain.interface.w3.eth.getBalance(policy_manager.address)

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
    assert node_balance + value == testerchain.interface.w3.eth.getBalance(node1)
    assert value == testerchain.interface.w3.eth.getBalance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert node1 == event_args['node']
    assert node1 == event_args['recipient']
    assert 120 == event_args['value']

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, int(0.5 * rate), [node2, node3]) \
        .transact({'from': client, 'value': int(2 * value + rate)})
    testerchain.wait_for_receipt(tx)

    # Mint some periods
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period, 5).transact({'from': node2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    period += 5
    assert 90 == policy_manager.functions.nodes(node2).call()[REWARD_FIELD]

    # Mint more periods
    for x in range(6):
        tx = escrow.functions.mint(period, 1).transact({'from': node2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
        period += 1
    assert 210 == policy_manager.functions.nodes(node2).call()[REWARD_FIELD]

    # Withdraw ETH for first node
    node_balance = testerchain.interface.w3.eth.getBalance(node1)
    node_2_balance = testerchain.interface.w3.eth.getBalance(node2)
    tx = policy_manager.functions.withdraw(node1).transact({'from': node2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert node_balance + 210 == testerchain.interface.w3.eth.getBalance(node1)
    assert node_2_balance == testerchain.interface.w3.eth.getBalance(node2)
    assert value + 210 == testerchain.interface.w3.eth.getBalance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert node2 == event_args['node']
    assert node1 == event_args['recipient']
    assert 210 == event_args['value']


@pytest.mark.slow
def test_refund(testerchain, escrow, policy_manager):
    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(hours=1)

    creator = testerchain.interface.w3.eth.accounts[0]
    client = testerchain.interface.w3.eth.accounts[1]
    node1 = testerchain.interface.w3.eth.accounts[3]
    node2 = testerchain.interface.w3.eth.accounts[4]
    node3 = testerchain.interface.w3.eth.accounts[5]
    client_balance = testerchain.interface.w3.eth.getBalance(client)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, int(0.5 * rate), [node1]) \
        .transact({'from': client, 'value': int(value + 0.5 * rate), 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(escrow.functions.getCurrentPeriod().call() - 1).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=9)
    # Check that methods only calculates value
    tx = policy_manager.functions.calculateRefundValue(policy_id).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.calculateRefundValue(policy_id, node1).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 210 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - 210 == testerchain.interface.w3.eth.getBalance(client)
    assert 190 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': client})
    assert 190 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': client})

    # Call refund, the result must be almost all ETH without payment for one period
    tx = policy_manager.functions.refund(policy_id).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 20 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - 20 == testerchain.interface.w3.eth.getBalance(client)
    assert client == policy_manager.functions.policies(policy_id).call()[CLIENT_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 190 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert 190 == event_args['value']

    testerchain.time_travel(hours=1)
    assert 20 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': client})
    assert 20 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': client})

    # Call refund, last period must be refunded
    tx = policy_manager.functions.refund(policy_id).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance == testerchain.interface.w3.eth.getBalance(client)
    assert policy_manager.functions.policies(policy_id).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 1 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 20 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 1 == len(events)
    events = policy_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert 20 == event_args['value']

    # Can't refund again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, node1).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, NULL_ADDR).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id).call({'from': client})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': client})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, NULL_ADDR).call({'from': client})

    # Create new policy
    testerchain.time_travel(hours=1)
    period = escrow.call().getCurrentPeriod()
    tx = escrow.transact().setLastActivePeriod(period)
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, int(0.5 * rate), [node1, node2, node3]) \
        .transact({'from': client, 'value': int(3 * value + 1.5 * rate), 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    # Nothing to refund because nodes are active in the current period
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': client})
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': client})
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 3 * value + 1.5 * rate == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - int(3 * value + 1.5 * rate) == testerchain.interface.w3.eth.getBalance(client)

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 0 == event_args['value']

    event_args = events[2]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert 0 == event_args['value']

    event_args = events[3]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert 0 == event_args['value']

    event_args = events[4]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 0 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert 0 == event_args['value']

    # Try to refund nonexistent policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_3).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': client})
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
    assert 90 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    testerchain.time_travel(hours=10)
    assert 360 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': client})
    assert 120 == policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': client})

    # Refund for only inactive periods
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 2 * value + 90 + rate == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - (2 * value + 90 + rate) == testerchain.interface.w3.eth.getBalance(client)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 120 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)

    # Can't refund arrangement again because it's disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2, NULL_ADDR).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': client})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, NULL_ADDR).call({'from': client})

    # But can refund others arrangements
    assert 240 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': client})
    assert 120 == policy_manager.functions.calculateRefundValue(policy_id_2, node2).call({'from': client})
    assert 120 == policy_manager.functions.calculateRefundValue(policy_id_2, node3).call({'from': client})
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 3 * 90 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - 3 * 90 == testerchain.interface.w3.eth.getBalance(client)
    assert policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[2]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert 120 == event_args['value']

    event_args = events[3]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert 120 == event_args['value']

    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)
    events = policy_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert 2 * 120 == event_args['value']

    # Create new policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_3, number_of_periods, int(0.5 * rate), [node1])\
        .transact({'from': client, 'value': int(value + 0.5 * rate), 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    # Mint some periods
    period += 1
    tx = escrow.functions.pushDowntimePeriod(period - 1, period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    for x in range(3):
        period += 1
        tx = escrow.functions.mint(period, 1).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(period).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 150 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Policy owner revokes policy
    testerchain.time_travel(hours=4)
    assert 30 == policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': client})
    assert 30 == policy_manager.functions.calculateRefundValue(policy_id_3, node1).call({'from': client})

    tx = policy_manager.functions.revokePolicy(policy_id_3).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 60 + 3 * 90 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - (60 + 3 * 90) == testerchain.interface.w3.eth.getBalance(client)
    assert policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]

    events = arrangement_refund_log.get_all_entries()
    assert 5 == len(events)
    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)

    events = arrangement_revoked_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 150 == event_args['value']

    events = policy_revoked_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert 150 == event_args['value']

    # Minting is useless after policy is revoked
    for x in range(20):
        period += 1
        tx = escrow.functions.mint(period, 1).transact({'from': node1})
        testerchain.wait_for_receipt(tx)
    assert 150 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    events = policy_created_log.get_all_entries()
    assert 3 == len(events)
