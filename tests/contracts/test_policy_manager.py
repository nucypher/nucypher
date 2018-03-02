import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def escrow(web3, chain):
    creator = web3.eth.accounts[0]
    node = web3.eth.accounts[1]
    # Creator deploys the escrow
    escrow, _ = chain.provider.get_or_deploy_contract(
        'MinersEscrowForPolicyMock', deploy_args=[node, MINUTES_IN_PERIOD],
        deploy_transaction={'from': creator})
    return escrow


@pytest.fixture()
def policy_manager(web3, chain, escrow):
    creator = web3.eth.accounts[0]
    client = web3.eth.accounts[2]

    # Creator deploys the policy manager
    policy_manager, _ = chain.provider.get_or_deploy_contract(
        'PolicyManager', deploy_args=[escrow.address],
        deploy_transaction={'from': creator})
    tx = escrow.transact({'from': creator}).setPolicyManager(policy_manager.address)
    chain.wait.for_receipt(tx)

    # Give client some ether
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': client, 'value': 10000})
    chain.wait.for_receipt(tx)

    return policy_manager


def wait_time(chain, wait_periods):
    web3 = chain.web3
    step = 1
    end_timestamp = web3.eth.getBlock(web3.eth.blockNumber).timestamp + wait_periods * 60 * MINUTES_IN_PERIOD
    while web3.eth.getBlock(web3.eth.blockNumber).timestamp < end_timestamp:
        chain.wait.for_block(web3.eth.blockNumber + step)


MINUTES_IN_PERIOD = 10
policy_id = bytes([1])
policy_id_2 = bytes([2])
rate = 20
number_of_periods = 10
value = rate * number_of_periods


def test_create_revoke(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    node = web3.eth.accounts[1]
    client = web3.eth.accounts[2]
    bad_node = web3.eth.accounts[3]
    client_balance = web3.eth.getBalance(client)

    # Try create policy for bad node
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': client, 'value': value})\
            .createPolicy(policy_id, bad_node, 1)
        chain.wait.for_receipt(tx)
    # Try create policy with no ETH
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': client})\
            .createPolicy(policy_id, node, 1)
        chain.wait.for_receipt(tx)

    # Create policy
    period = escrow.call().getCurrentPeriod()
    tx = policy_manager.transact({'from': client, 'value': value, 'gas_price': 0})\
        .createPolicy(policy_id, node, number_of_periods)
    chain.wait.for_receipt(tx)
    policy = policy_manager.call().policies(policy_id)
    assert 200 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 200 == web3.eth.getBalance(client)
    assert client == policy[0]
    assert node == policy[1]
    assert rate == policy[2]
    assert period + 1 == policy[3]
    assert period + 10 == policy[4]

    # Try to create policy again
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': client, 'value': value}) \
            .createPolicy(policy_id, node, number_of_periods)
        chain.wait.for_receipt(tx)

    # Only client can revoke policy
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': creator}).revokePolicy(policy_id)
        chain.wait.for_receipt(tx)
    tx = policy_manager.transact({'from': client, 'gas_price': 0}).revokePolicy(policy_id)
    chain.wait.for_receipt(tx)
    policy = policy_manager.call().policies(policy_id)
    assert '0x' + '0' * 40 == policy[0]

    # Create another policy
    period = escrow.call().getCurrentPeriod()
    tx = policy_manager.transact({'from': client, 'value': value, 'gas_price': 0})\
        .createPolicy(policy_id_2, node, number_of_periods)
    chain.wait.for_receipt(tx)
    policy = policy_manager.call().policies(policy_id_2)
    assert 200 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 200 == web3.eth.getBalance(client)
    assert client == policy[0]
    assert node == policy[1]
    assert rate == policy[2]
    assert period + 1 == policy[3]
    assert period + 10 == policy[4]


def test_reward(web3, chain, escrow, policy_manager):
    node = web3.eth.accounts[1]
    client = web3.eth.accounts[2]
    node_balance = web3.eth.getBalance(node)

    # Create policy
    period = escrow.call().getCurrentPeriod()
    tx = policy_manager.transact({'from': client, 'value': value})\
        .createPolicy(policy_id, node, number_of_periods)
    chain.wait.for_receipt(tx)

    # Nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': node}).withdraw()
        chain.wait.for_receipt(tx)

    # Can't update reward directly
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': node}).updateReward(node, period + 1)
        chain.wait.for_receipt(tx)

    # Mint some periods
    for x in range(5):
        tx = escrow.transact({'from': node, 'gas_price': 0}).mint(period)
        chain.wait.for_receipt(tx)
        period += 1
    assert 80 == policy_manager.call().nodes(node)

    # Withdraw
    tx = policy_manager.transact({'from': node, 'gas_price': 0}).withdraw()
    chain.wait.for_receipt(tx)
    assert node_balance + 80 == web3.eth.getBalance(node)
    assert 120 == web3.eth.getBalance(policy_manager.address)

    # Mint more periods
    for x in range(20):
        tx = escrow.transact({'from': node, 'gas_price': 0}).mint(period)
        chain.wait.for_receipt(tx)
        period += 1
    assert 120 == policy_manager.call().nodes(node)

    # Withdraw
    tx = policy_manager.transact({'from': node, 'gas_price': 0}).withdraw()
    chain.wait.for_receipt(tx)
    assert node_balance + 200 == web3.eth.getBalance(node)
    assert 0 == web3.eth.getBalance(policy_manager.address)


def test_refund(web3, chain, escrow, policy_manager):
    node = web3.eth.accounts[1]
    client = web3.eth.accounts[2]
    client_balance = web3.eth.getBalance(client)

    # Create policy
    tx = policy_manager.transact({'from': client, 'value': value, 'gas_price': 0}) \
        .createPolicy(policy_id, node, number_of_periods)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().setLastActivePeriod(escrow.call().getCurrentPeriod())
    chain.wait.for_receipt(tx)

    # Wait and refund all
    wait_time(chain, 9)
    tx = policy_manager.transact({'from': client, 'gas_price': 0}).refund(policy_id)
    chain.wait.for_receipt(tx)
    assert 20 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 20 == web3.eth.getBalance(client)
    assert client == policy_manager.call().policies(policy_id)[0]
    wait_time(chain, 1)
    tx = policy_manager.transact({'from': client, 'gas_price': 0}).refund(policy_id)
    chain.wait.for_receipt(tx)
    assert 0 == web3.eth.getBalance(policy_manager.address)
    assert client_balance == web3.eth.getBalance(client)
    assert '0x' + '0' * 40 == policy_manager.call().policies(policy_id)[0]

    # Create policy again
    period = escrow.call().getCurrentPeriod()
    tx = policy_manager.transact({'from': client, 'value': value, 'gas_price': 0})\
        .createPolicy(policy_id, node, number_of_periods)
    chain.wait.for_receipt(tx)

    # Nothing to refund
    tx = policy_manager.transact({'from': client, 'gas_price': 0}).refund(policy_id)
    chain.wait.for_receipt(tx)
    assert 200 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 200 == web3.eth.getBalance(client)

    # Try to refund nonexistent policy
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': client}).refund(policy_id_2)
        chain.wait.for_receipt(tx)

    # Node try to refund by node
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': node}).refund(policy_id)
        chain.wait.for_receipt(tx)

    # Mint some periods and mark others as downtime periods
    period += 1
    tx = escrow.transact().mint(period)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().mint(period + 1)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().pushDowntimePeriod(period + 2, period + 3)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().mint(period + 4)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().pushDowntimePeriod(period + 5, period + 7)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().mint(period + 8)
    chain.wait.for_receipt(tx)
    tx = escrow.transact().setLastActivePeriod(period + 8)
    chain.wait.for_receipt(tx)
    assert 80 == policy_manager.call().nodes(node)

    # Wait and refund
    wait_time(chain, 10)
    tx = policy_manager.transact({'from': client, 'gas_price': 0}).refund(policy_id)
    chain.wait.for_receipt(tx)
    assert 80 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 80 == web3.eth.getBalance(client)
    assert '0x' + '0' * 40 == policy_manager.call().policies(policy_id)[0]

    # Create policy again
    period = escrow.call().getCurrentPeriod()
    tx = policy_manager.transact({'from': client, 'value': value, 'gas_price': 0})\
        .createPolicy(policy_id, node, number_of_periods)
    chain.wait.for_receipt(tx)

    # Mint some periods
    period += 1
    tx = escrow.transact().pushDowntimePeriod(period, period)
    chain.wait.for_receipt(tx)
    for x in range(3):
        period += 1
        tx = escrow.transact({'from': node}).mint(period)
        chain.wait.for_receipt(tx)
    tx = escrow.transact().setLastActivePeriod(period)
    chain.wait.for_receipt(tx)
    assert 140 == policy_manager.call().nodes(node)

    # Client revokes policy
    wait_time(chain, 4)
    tx = policy_manager.transact({'from': client, 'gas_price': 0}).revokePolicy(policy_id)
    chain.wait.for_receipt(tx)
    policy = policy_manager.call().policies(policy_id)
    assert 140 == web3.eth.getBalance(policy_manager.address)
    assert client_balance - 140 == web3.eth.getBalance(client)
    assert '0x' + '0' * 40 == policy[0]

    # Minting is useless after revoke
    for x in range(20):
        period += 1
        tx = escrow.transact({'from': node}).mint(period)
        chain.wait.for_receipt(tx)
    assert 140 == policy_manager.call().nodes(node)
