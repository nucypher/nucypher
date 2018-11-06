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
from web3.contract import Contract

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


secret = (123456).to_bytes(32, byteorder='big')
secret2 = (654321).to_bytes(32, byteorder='big')


POLICY_ID_LENGTH = 16
policy_id = os.urandom(POLICY_ID_LENGTH)
policy_id_2 = os.urandom(POLICY_ID_LENGTH)
policy_id_3 = os.urandom(POLICY_ID_LENGTH)
rate = 20
number_of_periods = 10
value = rate * number_of_periods


@pytest.mark.slow
def test_create_revoke(testerchain, escrow, policy_manager):
    creator, client, bad_node, node1, node2, node3, *everyone_else = testerchain.interface.w3.eth.accounts

    client_balance = testerchain.interface.w3.eth.getBalance(client)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')

    # Check registered nodes
    assert 0 < policy_manager.functions.nodes(node1).call()[LAST_MINED_PERIOD_FIELD]
    assert 0 < policy_manager.functions.nodes(node2).call()[LAST_MINED_PERIOD_FIELD]
    assert 0 < policy_manager.functions.nodes(node3).call()[LAST_MINED_PERIOD_FIELD]
    assert 0 == policy_manager.functions.nodes(bad_node).call()[LAST_MINED_PERIOD_FIELD]

    # Try to create policy for bad (unregistered) node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, 0, [bad_node])\
            .transact({'from': client, 'value': value})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, 0, [node1, bad_node])\
            .transact({'from': client, 'value': value})
        testerchain.wait_for_receipt(tx)

    # Try to create policy with no ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, 0, [node1]).transact({'from': client})
        testerchain.wait_for_receipt(tx)

    # Create policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, 0, [node1])\
        .transact({'from': client, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    # Check balances and policy info
    assert value == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - 200 == testerchain.interface.w3.eth.getBalance(client)
    policy = policy_manager.functions.policies(policy_id).call()
    assert client == policy[CLIENT_FIELD]
    assert rate == policy[RATE_FIELD]
    assert 0 == policy[FIRST_REWARD_FIELD]
    assert period + 1 == policy[START_PERIOD_FIELD]
    assert period + 10 == policy[LAST_PERIOD_FIELD]
    assert not policy[DISABLED_FIELD]
    assert 1 == policy_manager.functions.getArrangementsLength(policy_id).call()
    assert node1 == policy_manager.functions.getArrangementInfo(policy_id, 0).call()[0]

    events = policy_created_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']

    # Can't create policy with the same id
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, 0, [node1])\
            .transact({'from': client, 'value': value})
        testerchain.wait_for_receipt(tx)

    # Only policy owner can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.policies(policy_id).call()[DISABLED_FIELD]

    events = policy_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert value == event_args['value']
    events = arrangement_revoked_log.get_all_entries()
    assert 1 == len(events)

    event_args = events[0]['args']
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert value == event_args['value']

    # Can't revoke again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id, node1).transact({'from': client})
        testerchain.wait_for_receipt(tx)

    # Create new policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, 0, [node1, node2, node3])\
        .transact({'from': client, 'value': 6 * value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 6 * value == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - 6 * value == testerchain.interface.w3.eth.getBalance(client)
    policy = policy_manager.functions.policies(policy_id_2).call()
    assert client == policy[CLIENT_FIELD]
    assert 2 * rate == policy[RATE_FIELD]
    assert 0 == policy[FIRST_REWARD_FIELD]
    assert period + 1 == policy[START_PERIOD_FIELD]
    assert period + 10 == policy[LAST_PERIOD_FIELD]
    assert not policy[DISABLED_FIELD]

    events = policy_created_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']

    # Can't revoke nonexistent arrangement
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, testerchain.interface.w3.eth.accounts[6])\
            .transact({'from': client})
        testerchain.wait_for_receipt(tx)
    # Can't revoke null arrangement (also it's nonexistent)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, NULL_ADDR).transact({'from': client})
        testerchain.wait_for_receipt(tx)

    # Revoke only one arrangement
    tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 4 * value == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - 4 * value == testerchain.interface.w3.eth.getBalance(client)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 2 * value == event_args['value']

    # Can't revoke again because arrangement is disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    # Can't revoke null arrangement (it's nonexistent)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, NULL_ADDR).transact({'from': client})
        testerchain.wait_for_receipt(tx)

    # Revoke policy with remaining arrangements
    tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance == testerchain.interface.w3.eth.getBalance(client)
    assert policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[2]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert 2 * value == event_args['value']

    event_args = events[3]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert 2 * value == event_args['value']
    events = policy_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']

    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert 4 * value == event_args['value']

    # Can't revoke policy again because policy and all arrangements are disabled
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': client})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client})
        testerchain.wait_for_receipt(tx)

    # Can't create policy with wrong ETH value - when reward is not calculated by formula:
    # numberOfNodes * (firstPartialReward + rewardRate * numberOfPeriods)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 10, 0, [node1]).transact({'from': client, 'value': 11})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 10, 1, [node1]).transact({'from': client, 'value': 22})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 10, 1, [node1]).transact({'from': client, 'value': 11})
        testerchain.wait_for_receipt(tx)

    # Set minimum reward rate for nodes
    tx = policy_manager.functions.setMinRewardRate(10).transact({'from': node1})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.setMinRewardRate(20).transact({'from': node2})
    testerchain.wait_for_receipt(tx)
    assert 10 == policy_manager.functions.nodes(node1).call()[MIN_REWARD_RATE_FIELD]
    assert 20 == policy_manager.functions.nodes(node2).call()[MIN_REWARD_RATE_FIELD]

    # Try to create policy with low rate
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 1, 0, [node1])\
            .transact({'from': client, 'value': 5})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 1, 0, [node1, node2])\
            .transact({'from': client, 'value': 30})
        testerchain.wait_for_receipt(tx)

    # Create new policy with payment for the first period
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_3, number_of_periods, int(0.5 * rate), [node1, node2, node3])\
        .transact({'from': client,
                   'value': int((0.5 * rate + rate * number_of_periods) * 3),
                   'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 3 * value + 1.5 * rate == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - int(3 * value + 1.5 * rate) == testerchain.interface.w3.eth.getBalance(client)
    policy = policy_manager.functions.policies(policy_id_3).call()
    assert client == policy[CLIENT_FIELD]
    assert rate == policy[RATE_FIELD]
    assert 0.5 * rate == policy[FIRST_REWARD_FIELD]
    assert period + 1 == policy[START_PERIOD_FIELD]
    assert period + 10 == policy[LAST_PERIOD_FIELD]
    assert not policy[DISABLED_FIELD]

    events = policy_created_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']

    # Revoke only one arrangement
    tx = policy_manager.functions.revokeArrangement(policy_id_3, node1).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 2 * value + rate == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance - (2 * value + rate) == testerchain.interface.w3.eth.getBalance(client)
    assert not policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert value + 0.5 * rate == event_args['value']

    # Revoke policy
    tx = policy_manager.functions.revokePolicy(policy_id_3).transact({'from': client, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert client_balance == testerchain.interface.w3.eth.getBalance(client)
    assert policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[5]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert value + 0.5 * rate == event_args['value']

    event_args = events[6]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert value + 0.5 * rate == event_args['value']

    events = policy_revoked_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert 2 * value + rate == event_args['value']

    events = arrangement_refund_log.get_all_entries()
    assert 0 == len(events)
    events = policy_refund_log.get_all_entries()
    assert 0 == len(events)


@pytest.mark.slow
def test_upgrading(testerchain):
    creator = testerchain.interface.w3.eth.accounts[0]

    secret_hash = testerchain.interface.w3.sha3(secret)
    secret2_hash = testerchain.interface.w3.sha3(secret2)

    # Deploy contracts
    escrow1, _ = testerchain.interface.deploy_contract('MinersEscrowForPolicyMock', 1)
    escrow2, _ = testerchain.interface.deploy_contract('MinersEscrowForPolicyMock', 1)
    address1 = escrow1.address
    address2 = escrow2.address
    contract_library_v1, _ = testerchain.interface.deploy_contract('PolicyManager', address1)
    dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract_library_v1.address, secret_hash)

    # Deploy second version of the contract
    contract_library_v2, _ = testerchain.interface.deploy_contract('PolicyManagerV2Mock', address2)
    contract = testerchain.interface.w3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Upgrade to the second version
    assert address1 == contract.functions.escrow().call()
    tx = dispatcher.functions.upgrade(contract_library_v2.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check constructor and storage values
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert address2 == contract.functions.escrow().call()
    # Check new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = testerchain.interface.deploy_contract('PolicyManagerBad', address2)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address, secret2, secret_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret2, secret_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback(secret2, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert address1 == contract.functions.escrow().call()
    # After rollback new ABI is unavailable
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret, secret2_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
