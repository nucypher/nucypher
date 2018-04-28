import pytest
from eth_tester.exceptions import TransactionFailed
import os

from web3.contract import Contract

MINERS_LENGTH = 0
MINER = 1
VALUE_FIELD = 2
DECIMALS_FIELD = 3
LOCKED_VALUE_FIELD = 4
RELEASE_FIELD = 5
MAX_RELEASE_PERIODS_FIELD = 6
RELEASE_RATE_FIELD = 7
CONFIRMED_PERIODS_FIELD_LENGTH = 8
CONFIRMED_PERIOD_FIELD = 9
CONFIRMED_PERIOD_LOCKED_VALUE_FIELD = 10
LAST_ACTIVE_PERIOD_FIELD = 11
DOWNTIME_FIELD_LENGTH = 12
DOWNTIME_START_PERIOD_FIELD = 13
DOWNTIME_END_PERIOD_FIELD = 14
MINER_IDS_FIELD_LENGTH = 15
MINER_ID_FIELD = 16

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
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    contract, _ = chain.provider.deploy_contract('NuCypherKMSToken', 2 * 10 ** 9)
    return contract


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    contract, _ = chain.provider.deploy_contract(
        'MinersEscrow',
        token.address,
        1,
        4 * 2 * 10 ** 7,
        4,
        4,
        2,
        100,
        2000)

    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

    # Deploy second version of the government contract
    contract = web3.eth.contract(abi=contract.abi, address=dispatcher.address, ContractFactoryClass=Contract)
    return contract


@pytest.fixture()
def policy_manager(web3, chain, escrow):
    creator = web3.eth.accounts[0]

    # Creator deploys the policy manager
    contract, _ = chain.provider.deploy_contract('PolicyManager', escrow.address)
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

    # Deploy second version of the government contract
    contract = web3.eth.contract(abi=contract.abi, address=dispatcher.address, ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)

    return contract


def wait_time(chain, wait_hours):
    web3 = chain.w3
    step = 50
    end_timestamp = web3.eth.getBlock(web3.eth.blockNumber).timestamp + wait_hours * 60 * 60
    while web3.eth.getBlock(web3.eth.blockNumber).timestamp < end_timestamp:
        chain.wait.for_block(web3.eth.blockNumber + step)


def test_all(web3, chain, token, escrow, policy_manager):
    creator, ursula1, ursula2, ursula3, ursula4, alice1, alice2, *everyone_else = web3.eth.accounts

    # Give clients some ether
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': alice1, 'value': 10 ** 10})
    chain.wait_for_receipt(tx)
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': alice2, 'value': 10 ** 10})
    chain.wait_for_receipt(tx)

    # Give Ursula and Alice some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(alice1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(alice2, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(ursula1).call()
    assert 10000 == token.functions.balanceOf(alice1).call()
    assert 10000 == token.functions.balanceOf(alice2).call()

    # Ursula give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Initialize escrow
    reward = 10 ** 9
    tx = token.functions.transfer(escrow.address, reward).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Deposit some tokens to the user escrow and lock them
    user_escrow_1, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address)
    tx = user_escrow_1.functions.transferOwnership(ursula3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.approve(user_escrow_1.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.initialDeposit(10000, 20 * 60 * 60).transact({'from': creator})
    chain.wait_for_receipt(tx)
    user_escrow_2, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address)
    tx = user_escrow_2.functions.transferOwnership(ursula4).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.approve(user_escrow_2.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = user_escrow_2.functions.initialDeposit(10000, 20 * 60 * 60).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(user_escrow_1.address).call()
    assert ursula3 == user_escrow_1.functions.owner().call()
    assert 10000 >= user_escrow_1.functions.getLockedTokens().call()
    assert 9500 <= user_escrow_1.functions.getLockedTokens().call()
    assert 10000 == token.functions.balanceOf(user_escrow_2.address).call()
    assert ursula4 == user_escrow_2.functions.owner().call()
    assert 10000 >= user_escrow_2.functions.getLockedTokens().call()
    assert 9500 <= user_escrow_2.functions.getLockedTokens().call()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula4).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_2.address).call()
    assert 0 == escrow.functions.getLockedTokens(everyone_else[0]).call()

    # Ursula can't deposit and lock too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And can't deposit and lock too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(2001, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.functions.approve(escrow.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Deposit tokens for 1 owner
    tx = escrow.functions.preDeposit([ursula2], [1000], [10]).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert reward + 1000 == token.functions.balanceOf(escrow.address).call()
    assert 1000 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula2, 0).call())
    assert 1000 == escrow.functions.getLockedTokens(ursula2).call()
    assert 10 == web3.toInt(escrow.functions.getMinerInfo(MAX_RELEASE_PERIODS_FIELD, ursula2, 0).call())

    # Can't pre-deposit tokens again for same owner
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula2], [1000], [10]).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Can't pre-deposit tokens with too low or too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula3], [1], [10]).transact({'from': creator})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula3], [10**6], [10]).transact({'from': creator})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula3], [500], [1]).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Ursula transfer some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 10).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert reward + 2000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1000 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.calculateLockedTokens(ursula1, 2).call()

    # Wait 1 period and deposit from one more Ursula
    chain.time_travel(hours=1)
    tx = user_escrow_1.functions.minerDeposit(1000, 10).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    assert 1000 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, user_escrow_1.address, 0).call())
    assert 1000 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 10 == web3.toInt(escrow.functions.getMinerInfo(MAX_RELEASE_PERIODS_FIELD, user_escrow_1.address, 0).call())
    assert 0 == web3.toInt(escrow.functions.getMinerInfo(RELEASE_FIELD, user_escrow_1.address, 0).call())
    assert reward + 3000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(user_escrow_1.address).call()

    # Only user can deposit tokens to the miner escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_1.functions.minerDeposit(1000, 5).transact({'from': creator})
        chain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_1.functions.minerDeposit(10000, 5).transact({'from': ursula3})
        chain.wait_for_receipt(tx)

    # Confirm activity
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.confirmActivity().transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.confirmActivity().transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    # Create policies
    policy_id_1 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_1, 5, [ursula1, ursula2]).transact({'from': alice1, 'value': 2 * 1000, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_2 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_2, 5, [ursula2, user_escrow_1.address]).transact({'from': alice1, 'value': 2 * 1000, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_3 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_3, 5, [ursula1, user_escrow_1.address]).transact({'from': alice2, 'value': 2 * 1000, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_4 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_4, 5, [ursula2, user_escrow_1.address]).transact({'from': alice2, 'value': 2 * 1000, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_5 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_5, 5, [ursula1, ursula2]).transact({'from': alice2, 'value': 2 * 1000, 'gas_price': 0})

    chain.wait_for_receipt(tx)

    # Only Alice can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    alice2_balance = web3.eth.getBalance(alice2)
    tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice2, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 8000 == web3.eth.getBalance(policy_manager.address)
    assert alice2_balance + 2000 == web3.eth.getBalance(alice2)
    assert 1 == web3.toInt(policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_5, NULL_ADDR).call())

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice2})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_5, ursula1).transact({'from': alice2})
        chain.wait_for_receipt(tx)

    alice1_balance = web3.eth.getBalance(alice1)
    tx = policy_manager.functions.revokeArrangement(policy_id_2, ursula2).transact({'from': alice1, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    assert 7000 == web3.eth.getBalance(policy_manager.address)
    assert alice1_balance + 1000 == web3.eth.getBalance(alice1)
    assert 0 == web3.toInt(
        policy_manager.functions.getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).call())

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, ursula2).transact({'from': alice1})
        chain.wait_for_receipt(tx)

    # Wait, confirm activity, mint
    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.confirmActivity().transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    chain.time_travel(hours=1)
    tx = policy_manager.functions.revokeArrangement(policy_id_3, user_escrow_1.address).transact({'from': alice2, 'gas_price': 0})

    chain.wait_for_receipt(tx)

    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.confirmActivity().transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    # Withdraw reward and refund
    chain.time_travel(hours=3)
    ursula1_balance = web3.eth.getBalance(ursula1)
    tx = policy_manager.functions.withdraw().transact({'from': ursula1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert ursula1_balance < web3.eth.getBalance(ursula1)
    ursula2_balance = web3.eth.getBalance(ursula2)
    tx = policy_manager.functions.withdraw().transact({'from': ursula2, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert ursula2_balance < web3.eth.getBalance(ursula2)
    user_escrow_1_balance = web3.eth.getBalance(user_escrow_1.address)
    tx = user_escrow_1.functions.policyRewardWithdraw().transact({'from': ursula3, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert user_escrow_1_balance < web3.eth.getBalance(user_escrow_1.address)

    alice1_balance = web3.eth.getBalance(alice1)
    tx = policy_manager.functions.refund(policy_id_1).transact({'from': alice1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert alice1_balance < web3.eth.getBalance(alice1)
    alice1_balance = web3.eth.getBalance(alice1)
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': alice1, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert alice1_balance < web3.eth.getBalance(alice1)
    alice2_balance = web3.eth.getBalance(alice2)
    tx = policy_manager.functions.refund(policy_id_3).transact({'from': alice2, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert alice2_balance == web3.eth.getBalance(alice2)
    tx = policy_manager.functions.refund(policy_id_4).transact({'from': alice2, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert alice2_balance < web3.eth.getBalance(alice2)

    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.switchLock().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.switchLock().transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    # Unlock and withdraw all tokens in MinersEscrow
    for index in range(9):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)
        tx = escrow.functions.confirmActivity().transact({'from': ursula2})
        chain.wait_for_receipt(tx)
        tx = user_escrow_1.functions.confirmActivity().transact({'from': ursula3})
        chain.wait_for_receipt(tx)
        chain.time_travel(hours=1)

    chain.time_travel(hours=1)
    tx = escrow.functions.mint().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.mint().transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula4).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_2.address).call()

    tokens_amount = web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula1, 0).call())
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tokens_amount = web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula2, 0).call())
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tokens_amount = web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, user_escrow_1.address, 0).call())
    tx = user_escrow_1.functions.minerWithdraw(tokens_amount).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    assert 10000 < token.functions.balanceOf(ursula1).call()
    assert 1000 < token.functions.balanceOf(ursula2).call()
    assert 10000 < token.functions.balanceOf(user_escrow_1.address).call()

    # Unlock and withdraw all tokens in UserEscrow
    chain.time_travel(hours=1)
    assert 0 == user_escrow_1.functions.getLockedTokens().call()
    assert 0 == user_escrow_2.functions.getLockedTokens().call()
    tokens_amount = token.functions.balanceOf(user_escrow_1.address).call()
    tx = user_escrow_1.functions.withdraw(tokens_amount).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    tokens_amount = token.functions.balanceOf(user_escrow_2.address).call()
    tx = user_escrow_2.functions.withdraw(tokens_amount).transact({'from': ursula4})
    chain.wait_for_receipt(tx)
    assert 10000 < token.functions.balanceOf(ursula3).call()
    assert 10000 == token.functions.balanceOf(ursula4).call()
