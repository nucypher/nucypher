import pytest
from eth_tester.exceptions import TransactionFailed
import os
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


@pytest.fixture()
def escrow(chain):
    # Creator deploys the escrow
    escrow, _ = chain.interface.deploy_contract('MinersEscrowForPolicyMock', 1)
    return escrow


@pytest.fixture(params=[False, True])
def policy_manager(web3, chain, escrow, request):
    creator, client, bad_node, node1, node2, node3, *everyone_else = web3.eth.accounts

    # Creator deploys the policy manager
    contract, _ = chain.interface.deploy_contract('PolicyManager', escrow.address)

    # Give client some ether
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': client, 'value': 10000})
    chain.wait_for_receipt(tx)

    if request.param:
        dispatcher, _ = chain.interface.deploy_contract('Dispatcher', contract.address)

        # Deploy second version of the government contract
        contract = web3.eth.contract(
            abi=contract.abi,
            address=dispatcher.address,
            ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Register nodes
    tx = escrow.functions.register(node1).transact()
    chain.wait_for_receipt(tx)
    tx = escrow.functions.register(node2).transact()
    chain.wait_for_receipt(tx)
    tx = escrow.functions.register(node3).transact()
    chain.wait_for_receipt(tx)

    return contract


policy_id = os.urandom(20)
policy_id_2 = os.urandom(20)
policy_id_3 = os.urandom(20)
rate = 20
number_of_periods = 10
value = rate * number_of_periods


@pytest.mark.slow
def test_create_revoke(web3, chain, escrow, policy_manager):
    creator, client, bad_node, node1, node2, node3, *everyone_else = web3.eth.accounts

    client_balance = web3.eth.getBalance(client)
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

    # Try create policy for bad node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, 0, [bad_node]).transact({'from': client, 'value': value})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, 0, [node1, bad_node]).transact({'from': client, 'value': value})
        chain.wait_for_receipt(tx)

    # Try create policy with no ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, 1, 0, [node1]).transact({'from': client})
        chain.wait_for_receipt(tx)

    # Create policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, 0, [node1]).transact({'from': client, 'value': value, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    assert value == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 200 == web3.eth.getBalance(client)
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
    # assert node1 == event_args['nodes'][0]

    # Try to create policy again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, 0, [node1]).transact({'from': client, 'value': value})
        chain.wait_for_receipt(tx)

    # Only client can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': creator})
        chain.wait_for_receipt(tx)
    tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
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

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    # Create another policy
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, 0, [node1, node2, node3]).transact({'from': client, 'value': 6 * value, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 6 * value == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 6 * value == web3.eth.getBalance(client)
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
    # assert node == event_args['node']

    # Can't revoke nonexistent arrangement
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, web3.eth.accounts[6]).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, NULL_ADDR).transact({'from': client})
        chain.wait_for_receipt(tx)

    tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 4 * value == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 4 * value == web3.eth.getBalance(client)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert policy_id_2 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert 2 * value == event_args['value']

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, NULL_ADDR).transact({'from': client})
        chain.wait_for_receipt(tx)

    tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == web3.eth.getBalance(policy_manager.address)
    assert client_balance == web3.eth.getBalance(client)
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

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_2).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, node1).transact({'from': client})
        chain.wait_for_receipt(tx)

    # Try to create policy with wrong value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 10, 0, [node1]).transact({'from': client, 'value': 11})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 10, 1, [node1]).transact({'from': client, 'value': 22})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 10, 1, [node1]).transact({'from': client, 'value': 11})
        chain.wait_for_receipt(tx)

    # Set minimum reward rate for nodes
    tx = policy_manager.functions.setMinRewardRate(10).transact({'from': node1})
    chain.wait_for_receipt(tx)
    tx = policy_manager.functions.setMinRewardRate(20).transact({'from': node2})
    chain.wait_for_receipt(tx)
    assert 10 == policy_manager.functions.nodes(node1).call()[MIN_REWARD_RATE_FIELD]
    assert 20 == policy_manager.functions.nodes(node2).call()[MIN_REWARD_RATE_FIELD]

    # Try to create policy with low rate
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 1, 0, [node1]).transact({'from': client, 'value': 5})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.createPolicy(policy_id_3, 1, 0, [node1, node2]).transact({'from': client, 'value': 30})
        chain.wait_for_receipt(tx)

    # Create another policy with pay for first period
    # Reward rate is calculated as (firstReward + rewardRate * numberOfPeriods) * numberOfNodes
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_3, number_of_periods, int(0.5 * rate), [node1, node2, node3])\
        .transact({'from': client,
                   'value': int((0.5 * rate + rate * number_of_periods) * 3),
                   'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 3 * value + 1.5 * rate == web3.eth.getBalance(policy_manager.address)
    assert client_balance - int(3 * value + 1.5 * rate) == web3.eth.getBalance(client)
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
    # assert node == event_args['node']

    tx = policy_manager.functions.revokeArrangement(policy_id_3, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 2 * value + rate == web3.eth.getBalance(policy_manager.address)
    assert client_balance - (2 * value + rate) == web3.eth.getBalance(client)
    assert not policy_manager.functions.policies(policy_id_3).call()[DISABLED_FIELD]

    events = arrangement_revoked_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert policy_id_3 == event_args['policyId']
    assert client == event_args['client']
    assert node1 == event_args['node']
    assert value + 0.5 * rate == event_args['value']

    tx = policy_manager.functions.revokePolicy(policy_id_3).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == web3.eth.getBalance(policy_manager.address)
    assert client_balance == web3.eth.getBalance(client)
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
def test_reward(web3, chain, escrow, policy_manager):
    creator, client, bad_node, node1, node2, node3, *everyone_else = web3.eth.accounts
    node_balance = web3.eth.getBalance(node1)
    withdraw_log = policy_manager.events.Withdrawn.createFilter(fromBlock='latest')

    # Mint period without policies
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, 0, [node1, node3]).transact({'from': client, 'value': 2 * value})
    chain.wait_for_receipt(tx)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.withdraw().transact({'from': node1})
        chain.wait_for_receipt(tx)

    # Can't update reward directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.updateReward(node1, period + 1).transact({'from': node1})
        chain.wait_for_receipt(tx)
    # Can't register directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.register(bad_node, period).transact({'from': bad_node})
        chain.wait_for_receipt(tx)

    # Mint some periods
    tx = escrow.functions.mint(period, 5).transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    period += 5
    assert 80 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Withdraw
    tx = policy_manager.functions.withdraw().transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert node_balance + 80 == web3.eth.getBalance(node1)
    assert 120 + value == web3.eth.getBalance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert node1 == event_args['node']
    assert 80 == event_args['value']

    # Mint more periods
    for x in range(6):
        tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
        chain.wait_for_receipt(tx)
        period += 1
    assert 120 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]
    tx = escrow.functions.mint(period, 1).transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 120 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Withdraw
    tx = policy_manager.functions.withdraw().transact({'from': node1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert node_balance + value == web3.eth.getBalance(node1)
    assert value == web3.eth.getBalance(policy_manager.address)

    events = withdraw_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert node1 == event_args['node']
    assert 120 == event_args['value']

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, int(0.5 * rate), [node2, node3]) \
        .transact({'from': client, 'value': int(2 * value + rate)})
    chain.wait_for_receipt(tx)

    # Mint some periods
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.mint(period, 5).transact({'from': node2, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    period += 5
    assert 90 == policy_manager.functions.nodes(node2).call()[REWARD_FIELD]

    # Mint more periods
    for x in range(6):
        tx = escrow.functions.mint(period, 1).transact({'from': node2, 'gas_price': 0})
        chain.wait_for_receipt(tx)
        period += 1
    assert 210 == policy_manager.functions.nodes(node2).call()[REWARD_FIELD]


@pytest.mark.slow
def test_refund(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    client = web3.eth.accounts[1]
    node1 = web3.eth.accounts[3]
    node2 = web3.eth.accounts[4]
    node3 = web3.eth.accounts[5]
    client_balance = web3.eth.getBalance(client)
    policy_created_log = policy_manager.events.PolicyCreated.createFilter(fromBlock='latest')
    arrangement_revoked_log = policy_manager.events.ArrangementRevoked.createFilter(fromBlock='latest')
    policy_revoked_log = policy_manager.events.PolicyRevoked.createFilter(fromBlock='latest')
    arrangement_refund_log = policy_manager.events.RefundForArrangement.createFilter(fromBlock='latest')
    policy_refund_log = policy_manager.events.RefundForPolicy.createFilter(fromBlock='latest')

    # Create policy
    tx = policy_manager.functions.createPolicy(policy_id, number_of_periods, int(0.5 * rate), [node1]) \
        .transact({'from': client, 'value': int(value + 0.5 * rate), 'gas_price': 0})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(escrow.functions.getCurrentPeriod().call() - 1).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Wait and refund all
    chain.time_travel(hours=9)
    # Check that methods only calculates value
    tx = policy_manager.functions.calculateRefundValue(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    tx = policy_manager.functions.calculateRefundValue(policy_id, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 210 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 210 == web3.eth.getBalance(client)
    assert 190 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': client})
    assert 190 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': client})
    tx = policy_manager.functions.refund(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 20 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 20 == web3.eth.getBalance(client)
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

    chain.time_travel(hours=1)
    assert 20 == policy_manager.functions.calculateRefundValue(policy_id).call({'from': client})
    assert 20 == policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': client})
    tx = policy_manager.functions.refund(policy_id).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 0 == web3.eth.getBalance(policy_manager.address)
    assert client_balance == web3.eth.getBalance(client)
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

    # Can't refund again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, node1).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id, NULL_ADDR).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id).call({'from': client})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, node1).call({'from': client})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id, NULL_ADDR).call({'from': client})

    # Create policy again
    chain.time_travel(hours=1)
    period = escrow.call().getCurrentPeriod()
    tx = escrow.transact().setLastActivePeriod(period)
    chain.wait_for_receipt(tx)
    tx = policy_manager.functions.createPolicy(policy_id_2, number_of_periods, int(0.5 * rate), [node1, node2, node3]) \
        .transact({'from': client, 'value': int(3 * value + 1.5 * rate), 'gas_price': 0})
    chain.wait_for_receipt(tx)

    # Nothing to refund
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': client})
    assert 0 == policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': client})
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 3 * value + 1.5 * rate == web3.eth.getBalance(policy_manager.address)
    assert client_balance - int(3 * value + 1.5 * rate) == web3.eth.getBalance(client)

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
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': client})
    # Node try to refund by node
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2).transact({'from': node1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': node1})

    # Mint some periods and mark others as downtime periods
    tx = escrow.functions.mint(period, 1).transact({'from': node1})
    chain.wait_for_receipt(tx)
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
    assert 90 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Wait and refund
    chain.time_travel(hours=10)
    assert 360 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': client})
    assert 120 == policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': client})
    tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 2 * value + 90 + rate == web3.eth.getBalance(policy_manager.address)
    assert client_balance - (2 * value + 90 + rate) == web3.eth.getBalance(client)
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

    # Can't refund arrangement again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2, node1).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.refund(policy_id_2, NULL_ADDR).transact({'from': client})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, node1).call({'from': client})
    with pytest.raises((TransactionFailed, ValueError)):
        policy_manager.functions.calculateRefundValue(policy_id_2, NULL_ADDR).call({'from': client})

    # But can refund others
    assert 240 == policy_manager.functions.calculateRefundValue(policy_id_2).call({'from': client})
    assert 120 == policy_manager.functions.calculateRefundValue(policy_id_2, node2).call({'from': client})
    assert 120 == policy_manager.functions.calculateRefundValue(policy_id_2, node3).call({'from': client})
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 3 * 90 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 3 * 90 == web3.eth.getBalance(client)
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

    # Create policy again
    period = escrow.functions.getCurrentPeriod().call()
    tx = policy_manager.functions.createPolicy(policy_id_3, number_of_periods, int(0.5 * rate), [node1])\
        .transact({'from': client, 'value': int(value + 0.5 * rate), 'gas_price': 0})
    chain.wait_for_receipt(tx)

    # Mint some periods
    period += 1
    tx = escrow.functions.pushDowntimePeriod(period - 1, period).transact({'from': creator})
    chain.wait_for_receipt(tx)
    for x in range(3):
        period += 1
        tx = escrow.functions.mint(period, 1).transact({'from': node1})
        chain.wait_for_receipt(tx)
    tx = escrow.functions.setLastActivePeriod(period).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 150 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    # Client revokes policy
    chain.time_travel(hours=4)
    assert 30 == policy_manager.functions.calculateRefundValue(policy_id_3).call({'from': client})
    assert 30 == policy_manager.functions.calculateRefundValue(policy_id_3, node1).call({'from': client})
    tx = policy_manager.functions.revokePolicy(policy_id_3).transact({'from': client, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 60 + 3 * 90 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - (60 + 3 * 90) == web3.eth.getBalance(client)
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

    # Minting is useless after revoke
    for x in range(20):
        period += 1
        tx = escrow.functions.mint(period, 1).transact({'from': node1})
        chain.wait_for_receipt(tx)
    assert 150 == policy_manager.functions.nodes(node1).call()[REWARD_FIELD]

    events = policy_created_log.get_all_entries()
    assert 3 == len(events)


@pytest.mark.slow
def test_verifying_state(web3, chain):
    creator = web3.eth.accounts[0]

    # Deploy contracts
    escrow1, _ = chain.interface.deploy_contract('MinersEscrowForPolicyMock', 1)
    escrow2, _ = chain.interface.deploy_contract('MinersEscrowForPolicyMock', 1)
    address1 = escrow1.address
    address2 = escrow2.address
    contract_library_v1, _ = chain.interface.deploy_contract('PolicyManager', address1)
    dispatcher, _ = chain.interface.deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = chain.interface.deploy_contract('PolicyManagerV2Mock', address2)
    contract = web3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Upgrade to the second version
    assert address1 == contract.functions.escrow().call()
    tx = dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert address2 == contract.functions.escrow().call()
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.interface.deploy_contract('PolicyManagerBad', address2)
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
