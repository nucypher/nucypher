import pytest
from eth_tester.exceptions import TransactionFailed
import os
from web3.contract import Contract


CLIENT_FIELD = 0
INDEX_OF_DOWNTIME_PERIODS_FIELD = 1
LAST_REFUNDED_PERIOD_FIELD = 2
ARRANGEMENT_DISABLED_FIELD = 3
RATE_FIELD = 4
START_PERIOD_FIELD = 5
LAST_PERIOD_FIELD = 6
DISABLED_FIELD = 7

REWARD_FIELD = 0
REWARD_RATE_FIELD = 1
LAST_MINED_PERIOD_FIELD = 2
REWARD_DELTA_FIELD = 3

NULL_ADDR = '0x' + '0' * 40


@pytest.fixture()
def escrow(web3, chain):
    creator = web3.eth.accounts[0]
    node1 = web3.eth.accounts[3]
    node2 = web3.eth.accounts[4]
    node3 = web3.eth.accounts[5]
    # Creator deploys the escrow
    escrow, _ = chain.provider.deploy_contract('MinersEscrowForPolicyMock', [node1, node2, node3], MINUTES_IN_PERIOD)
    return escrow


@pytest.fixture(params=[False, True])
def policy_manager(web3, chain, escrow, request):
    creator = web3.eth.accounts[0]
    client = web3.eth.accounts[1]

    # Creator deploys the policy manager
    contract, _ = chain.provider.deploy_contract('PolicyManager', escrow.address)

    # Give client some ether
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': client, 'value': 10000})
    chain.wait_for_receipt(tx)

    if request.param:
        dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

        # Deploy second version of the government contract
        contract = web3.eth.contract(
            abi=contract.abi,
            address=dispatcher.address,
            ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)

    return contract


def wait_time(chain, wait_periods):
    chain.time_travel(seconds=wait_periods * 60 * MINUTES_IN_PERIOD)


MINUTES_IN_PERIOD = 10
policy_id = os.urandom(20)
policy_id_2 = os.urandom(20)
policy_id_3 = os.urandom(20)
rate = 20
number_of_periods = 10
value = rate * number_of_periods


def test_create_revoke(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    client = web3.eth.accounts[1]
    bad_node = web3.eth.accounts[2]
    node1 = web3.eth.accounts[3]
    node2 = web3.eth.accounts[4]
    node3 = web3.eth.accounts[5]
    client_balance = web3.eth.getBalance(client)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock=0)
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock=0)
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock=0)
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock=0)
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock=0)

    # Try create policy for bad node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, [bad_node]).transact({'from': client, 'value': value})
        chain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, [node1, bad_node]).transact({'from': client, 'value': value})
        chain.wait_for_receipt(tx)

    # Try create policy with no ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, [node1]).transact({'from': client})
        chain.wait_for_receipt(tx)

    # Create policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, [node1]).transact({'from': client, 'value': value, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    assert 200 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 200 == web3.eth.getBalance(client)
    # getPolicyInfo returns 32 bytes, where first 12 bytes is zero because of address format
    assert client == web3.toChecksumAddress(policy_manager.functions.getPolicyInfo(CLIENT_FIELD, policy_id, NULL_ADDR).call()[12:])
    assert rate == web3.toInt(policy_manager.functions.getPolicyInfo(RATE_FIELD, policy_id, NULL_ADDR).call())
    assert period + 1 == web3.toInt(policy_manager.functions.getPolicyInfo(START_PERIOD_FIELD, policy_id, NULL_ADDR).call())
    assert period + 10 == web3.toInt(policy_manager.functions.getPolicyInfo(LAST_PERIOD_FIELD, policy_id, NULL_ADDR).call())
    assert 0 == web3.toInt(policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id, NULL_ADDR).call())
    assert 1 == policy_manager.functions.getPolicyNodesLength(policy_id).call()
    assert node1 == policy_manager.functions.getPolicyNode(policy_id, 0).call()

    events = policy_created_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    # assert node == event_args['nodes'][0]

    # Try to create policy again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, [node1]).transact({'from': client, 'value': value})
        chain.wait_for_receipt(tx)

    # Only client can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': creator})
        chain.wait_for_receipt(tx)

    tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)

    assert 1 == web3.toInt(policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id, NULL_ADDR).call())

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

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    # Create another policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, [node1, node2, node3]).transact({'from': client, 'value': 3 * value, 'gas_price': 0})
    chain.wait_for_receipt(tx)

    assert 3 * value == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 3 * value == web3.eth.getBalance(client)
    assert client == web3.toChecksumAddress(
        policy_manager.functions.getPolicyInfo(CLIENT_FIELD, policy_id_2, NULL_ADDR).call()[12:])
    assert rate == web3.toInt(policy_manager.functions.getPolicyInfo(RATE_FIELD, policy_id_2, NULL_ADDR).call())
    assert period + 1 == web3.toInt(
        policy_manager.functions.getPolicyInfo(START_PERIOD_FIELD, policy_id_2, NULL_ADDR).call())
    assert period + 10 == web3.toInt(
        policy_manager.functions.getPolicyInfo(LAST_PERIOD_FIELD, policy_id_2, NULL_ADDR).call())
    assert 0 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).call())

    events = policy_created_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']

    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    # assert node == event_args['node']

    # Can't revoke nonexistent arrangement
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, web3.eth.accounts[6]).transact({'from': client})
        chain.wait_for_receipt(tx)

    tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)

    assert 2 * value == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 2 * value == web3.eth.getBalance(client)
    assert 0 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).call())

    events = arrangement_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']

    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert value == event_args['value']

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == web3.eth.getBalance(policy_manager.address)
    assert client_balance == web3.eth.getBalance(client)
    assert 1 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).call())

    events = arrangement_revoked_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[2]['args']

    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert value == event_args['value']
    event_args = events[3]['args']

    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert value == event_args['value']
    events = policy_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']

    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert 2 * value == event_args['value']

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    events = arrangement_refund_log.get_all_entries()
    assert 0 == len(events)
    events = policy_refund_log.get_all_entries()
    assert 0 == len(events)


def test_reward(web3, chain, escrow, policy_manager):
    client = web3.eth.accounts[1]
    node1 = web3.eth.accounts[3]
    node2 = web3.eth.accounts[4]
    node3 = web3.eth.accounts[5]
    node_balance = web3.eth.getBalance(node1)
    withdraw_log = policy_manager.events.Withdrawn.createFilter(fromBlock=0)

    # Mint period without policies
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == web3.toInt(policy_manager.functions.getNodeInfo(REWARD_FIELD, node1, 0).call())

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, [node1, node2, node3]).transact({'from': client, 'value': 3 * value})
    chain.wait_for_receipt(tx)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.withdraw().transact({'from': node1})
        chain.wait_for_receipt(tx)

    # Can't update reward directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.updateReward(node1, period + 1).transact({'from': node1})
        chain.wait_for_receipt(tx)

    # Mint some periods
    tx = escrow.functions.mint(period, 5).transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    period += 5
    assert 80 == web3.toInt(policy_manager.functions.getNodeInfo(REWARD_FIELD, node1, 0).call())

    # Withdraw
    tx = policy_manager.functions.withdraw().transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert node_balance + 80 == web3.eth.getBalance(node1)
    assert 120 + 2 * value == web3.eth.getBalance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert node1 == event_args['node']
    assert 80 == event_args['value']

    # Mint more periods
    for x in range(20):
        tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
        chain.wait_for_receipt(tx)
        period += 1
    assert 120 == web3.toInt(policy_manager.functions.getNodeInfo(REWARD_FIELD, node1, 0).call())

    # Withdraw
    tx = policy_manager.functions.withdraw().transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert node_balance + value == web3.eth.getBalance(node1)
    assert 2 * value == web3.eth.getBalance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert node1 == event_args['node']
    assert 120 == event_args['value']


def test_refund(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    client = web3.eth.accounts[1]
    node1 = web3.eth.accounts[3]
    node2 = web3.eth.accounts[4]
    node3 = web3.eth.accounts[5]
    client_balance = web3.eth.getBalance(client)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock=0)
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock=0)
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock=0)
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock=0)
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock=0)

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, [node1]).transact({'from': client, 'value': value, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(escrow.functions.getCurrentPeriod().call()).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Wait and refund all
    wait_time(chain, 9)
    tx =  policy_manager.functions.refund(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 20 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 20 == web3.eth.getBalance(client)
    assert client == web3.toChecksumAddress(
        policy_manager.functions.getPolicyInfo(CLIENT_FIELD, policy_id, NULL_ADDR).call()[12:])

    events = arrangement_refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 180 == event_args['value']
    events = policy_refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert 180 == event_args['value']

    wait_time(chain, 1)
    tx = policy_manager.functions.refund(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == web3.eth.getBalance(policy_manager.address)
    assert client_balance == web3.eth.getBalance(client)
    assert 1 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id, NULL_ADDR)).call()

    events = arrangement_refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 20 == event_args['value']
    events = policy_refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    
    assert policy_id == event_args['policyId']
    assert client == event_args['client']
    assert 20 == event_args['value']

    # Can't refund again
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  policy_manager.functions.refund(policy_id).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  policy_manager.functions.refund(policy_id, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    # Create policy again
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, [node1, node2, node3]).transact({'from': client, 'value': 3 * value, 'gas_price': 0})
    chain.wait_for_receipt(tx)

    # Nothing to refund
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 3 * value == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 3 * value == web3.eth.getBalance(client)
    events = arrangement_refund_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[2]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 0 == event_args['value']
    event_args = events[3]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert 0 == event_args['value']
    event_args = events[4]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert 0 == event_args['value']
    event_args = events[5]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 0 == event_args['value']
    events = policy_refund_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert 0 == event_args['value']

    # Try to refund nonexistent policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_3).transact({'from': client})
        chain.wait_for_receipt(tx)
    # Node try to refund by node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2).transact({'from': node1})
        chain.wait_for_receipt(tx)

    # Mint some periods and mark others as downtime periods
    period += 1
    tx = escrow.functions.mint(period, 2).transact({'from': node1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.pushDowntimePeriod(period + 2, period + 3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.mint(period + 4, 1).transact({'from': node1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.pushDowntimePeriod(period + 5, period + 7).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.mint(period + 8, 1).transact({'from': node1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(period + 8).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 80 == web3.toInt(policy_manager.functions.getNodeInfo(REWARD_FIELD, node1, 0).call())

    # Wait and refund
    wait_time(chain, 10)
    tx =  policy_manager.functions.refund(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 2 * value + 80 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - (2 * value + 80) == web3.eth.getBalance(client)
    assert 0 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).call())

    events = arrangement_refund_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 120 == event_args['value']
    events = policy_refund_log.get_all_entries()
    assert 3 == len(events)

    # Can't refund arrangement again
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  policy_manager.functions.refund(policy_id, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    # But can refund others
    tx =  policy_manager.functions.refund(policy_id_2).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 3 * 80 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 3 * 80 == web3.eth.getBalance(client)
    assert 1 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).call())

    events = arrangement_refund_log.get_all_entries()
    assert 9 == len(events)
    event_args = events[7]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node2 == event_args['node']
    assert 120 == event_args['value']
    event_args = events[8]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node3 == event_args['node']
    assert 120 == event_args['value']
    events = policy_refund_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert 2 * 120 == event_args['value']

    # Create policy again
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_3, number_of_periods, [node1]).transact({'from': client, 'value': value, 'gas_price': 0})
    chain.wait_for_receipt(tx)

    # Mint some periods
    period += 1
    tx = escrow.functions.pushDowntimePeriod(period, period).transact({'from': creator})
    chain.wait_for_receipt(tx)
    for x in range(3):
        period += 1
        tx = escrow.functions.mint(period, 1).transact({'from': node1})
        chain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(period).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 140 == web3.toInt(policy_manager.functions.getNodeInfo(REWARD_FIELD, node1, 0).call())

    # Client revokes policy
    wait_time(chain, 4)
    tx = policy_manager.functions.revokePolicy(policy_id_3).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 60 + 3 * 80 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - (60 + 3 * 80) == web3.eth.getBalance(client)
    assert 1 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_3, NULL_ADDR).call())

    events = arrangement_refund_log.get_all_entries()
    assert 9 == len(events)
    events = policy_refund_log.get_all_entries()
    assert 4 == len(events)
    events = arrangement_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 140 == event_args['value']
    events = policy_revoked_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert 140 == event_args['value']

    # Minting is useless after revoke
    for x in range(20):
        period += 1
        tx =  escrow.functions.mint(period, 1).transact({'from': node1})
        chain.wait_for_receipt(tx)
    assert 140 == web3.toInt(policy_manager.functions.getNodeInfo(REWARD_FIELD, node1, 0).call())

    events = policy_created_log.get_all_entries()
    assert 3 == len(events)


def test_verifying_state(web3, chain):
    creator = web3.eth.accounts[0]
    address1 = web3.eth.accounts[1]
    address2 = web3.eth.accounts[2]

    # Deploy contract
    contract_library_v1, _ = chain.provider.deploy_contract('PolicyManager', address1)
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = chain.provider.deploy_contract('PolicyManagerV2Mock', address2)
    contract = web3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Upgrade to the second version
    assert address1 == contract.functions.escrow().call()
    tx =  dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert address2 == contract.functions.escrow().call()
    tx =  contract.functions.setValueToCheck(3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.provider.deploy_contract('PolicyManagerBad', address2)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert address1 == contract.functions.escrow().call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
