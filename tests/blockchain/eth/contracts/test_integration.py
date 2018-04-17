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
    contract, _ = chain.provider.get_or_deploy_contract('NuCypherKMSToken', 2 * 10 ** 9)
    return contract


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    contract, _ = chain.provider.get_or_deploy_contract(
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
    contract, _ = chain.provider.get_or_deploy_contract('PolicyManager', escrow.address)
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

    # Deploy second version of the government contract
    contract = web3.eth.contract(abi=contract.abi, address=dispatcher.address, ContractFactoryClass=Contract)

    tx = escrow.transact({'from': creator}).setPolicyManager(contract.address)
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
    tx = token.transact({'from': creator}).transfer(ursula1, 10000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice1, 10000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice2, 10000)
    chain.wait_for_receipt(tx)
    assert 10000 == token.call().balanceOf(ursula1)
    assert 10000 == token.call().balanceOf(alice1)
    assert 10000 == token.call().balanceOf(alice2)

    # Ursula give Escrow rights to transfer
    tx = token.transact({'from': ursula1}).approve(escrow.address, 10000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': ursula2}).approve(escrow.address, 10000)
    chain.wait_for_receipt(tx)

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(1, 1)
        chain.wait_for_receipt(tx)

    # Initialize escrow
    reward = 10 ** 9
    tx = token.transact({'from': creator}).transfer(escrow.address, reward)
    chain.wait_for_receipt(tx)
    tx = escrow.transact().initialize()
    chain.wait_for_receipt(tx)

    # Deposit some tokens to the user escrow and lock them
    user_escrow_1, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address)
    tx = user_escrow_1.transact({'from': creator}).transferOwnership(ursula3)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).approve(user_escrow_1.address, 10000)
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': creator}).initialDeposit(10000, 20 * 60 * 60)
    chain.wait_for_receipt(tx)
    user_escrow_2, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address)
    tx = user_escrow_2.transact({'from': creator}).transferOwnership(ursula4)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).approve(user_escrow_2.address, 10000)
    chain.wait_for_receipt(tx)
    tx = user_escrow_2.transact({'from': creator}).initialDeposit(10000, 20 * 60 * 60)
    chain.wait_for_receipt(tx)
    assert 10000 == token.call().balanceOf(user_escrow_1.address)
    assert ursula3 == user_escrow_1.call().owner()
    assert 10000 >= user_escrow_1.call().getLockedTokens()
    assert 9500 <= user_escrow_1.call().getLockedTokens()
    assert 10000 == token.call().balanceOf(user_escrow_2.address)
    assert ursula4 == user_escrow_2.call().owner()
    assert 10000 >= user_escrow_2.call().getLockedTokens()
    assert 9500 <= user_escrow_2.call().getLockedTokens()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).withdraw(100)
        chain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).lock(500, 2)
        chain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.call().getLockedTokens(ursula1)
    assert 0 == escrow.call().getLockedTokens(ursula2)
    assert 0 == escrow.call().getLockedTokens(ursula3)
    assert 0 == escrow.call().getLockedTokens(ursula4)
    assert 0 == escrow.call().getLockedTokens(user_escrow_1.address)
    assert 0 == escrow.call().getLockedTokens(user_escrow_2.address)
    assert 0 == escrow.call().getLockedTokens(everyone_else[0])

    # Ursula can't deposit and lock too low value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(1, 1)
        chain.wait_for_receipt(tx)

    # And can't deposit and lock too high value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(2001, 1)
        chain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.transact({'from': creator}).approve(escrow.address, 10000)
    chain.wait_for_receipt(tx)

    # Deposit tokens for 1 owner
    tx = escrow.transact({'from': creator}).preDeposit([ursula2], [1000], [10])
    chain.wait_for_receipt(tx)
    assert reward + 1000 == token.call().balanceOf(escrow.address)
    assert 1000 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula2, 0).encode('latin-1'))
    assert 1000 == escrow.call().getLockedTokens(ursula2)
    assert 10 == web3.toInt(escrow.call().getMinerInfo(MAX_RELEASE_PERIODS_FIELD, ursula2, 0).encode('latin-1'))

    # Can't pre-deposit tokens again for same owner
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit([ursula2], [1000], [10])
        chain.wait_for_receipt(tx)

    # Can't pre-deposit tokens with too low or too high value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit([ursula3], [1], [10])
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit([ursula3], [10**6], [10])
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit([ursula3], [500], [1])
        chain.wait_for_receipt(tx)

    # Ursula transfer some tokens to the escrow and lock them
    tx = escrow.transact({'from': ursula1}).deposit(1000, 10)
    chain.wait_for_receipt(tx)
    assert reward + 2000 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(ursula1)
    assert 1000 == escrow.call().getLockedTokens(ursula1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula1, 2)

    # Wait 1 period and deposit from one more Ursula
    wait_time(chain, 1)
    tx = user_escrow_1.transact({'from': ursula3}).minerDeposit(1000, 10)
    chain.wait_for_receipt(tx)
    assert 1000 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, user_escrow_1.address, 0).encode('latin-1'))
    assert 1000 == escrow.call().getLockedTokens(user_escrow_1.address)
    assert 10 == web3.toInt(
        escrow.call().getMinerInfo(MAX_RELEASE_PERIODS_FIELD, user_escrow_1.address, 0).encode('latin-1'))
    assert 0 == web3.toInt(escrow.call().getMinerInfo(RELEASE_FIELD, user_escrow_1.address, 0).encode('latin-1'))
    assert reward + 3000 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(user_escrow_1.address)

    # Only user can deposit tokens to the miner escrow
    with pytest.raises(TransactionFailed):
        tx = user_escrow_1.transact({'from': creator}).minerDeposit(1000, 5)
        chain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises(TransactionFailed):
        tx = user_escrow_1.transact({'from': ursula3}).minerDeposit(10000, 5)
        chain.wait_for_receipt(tx)

    # Confirm activity
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)

    wait_time(chain, 1)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': ursula3}).confirmActivity()
    chain.wait_for_receipt(tx)

    wait_time(chain, 1)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': ursula3}).confirmActivity()
    chain.wait_for_receipt(tx)

    # Create policies
    policy_id_1 = os.urandom(20)
    tx = policy_manager.transact({'from': alice1, 'value': 2 * 1000, 'gas_price': 0}) \
        .createPolicy(policy_id_1, 5, [ursula1, ursula2])
    chain.wait_for_receipt(tx)
    policy_id_2 = os.urandom(20)
    tx = policy_manager.transact({'from': alice1, 'value': 2 * 1000, 'gas_price': 0}) \
        .createPolicy(policy_id_2, 5, [ursula2, user_escrow_1.address])
    chain.wait_for_receipt(tx)
    policy_id_3 = os.urandom(20)
    tx = policy_manager.transact({'from': alice2, 'value': 2 * 1000, 'gas_price': 0}) \
        .createPolicy(policy_id_3, 5, [ursula1, user_escrow_1.address])
    chain.wait_for_receipt(tx)
    policy_id_4 = os.urandom(20)
    tx = policy_manager.transact({'from': alice2, 'value': 2 * 1000, 'gas_price': 0}) \
        .createPolicy(policy_id_4, 5, [ursula2, user_escrow_1.address])
    chain.wait_for_receipt(tx)
    policy_id_5 = os.urandom(20)
    tx = policy_manager.transact({'from': alice2, 'value': 2 * 1000, 'gas_price': 0}) \
        .createPolicy(policy_id_5, 5, [ursula1, ursula2])
    chain.wait_for_receipt(tx)

    # Only Alice can revoke policy
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': ursula1}).revokePolicy(policy_id_5)
        chain.wait_for_receipt(tx)
    alice2_balance = web3.eth.getBalance(alice2)
    tx = policy_manager.transact({'from': alice2, 'gas_price': 0}).revokePolicy(policy_id_5)
    chain.wait_for_receipt(tx)
    assert 8000 == web3.eth.getBalance(policy_manager.address)
    assert alice2_balance + 2000 == web3.eth.getBalance(alice2)
    assert 1 == web3.toInt(
        policy_manager.call().getPolicyInfo(DISABLED_FIELD, policy_id_5, NULL_ADDR).encode('latin-1'))

    # Can't revoke again
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': alice2}).revokePolicy(policy_id_5)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': alice2}).revokeArrangement(policy_id_5, ursula1)
        chain.wait_for_receipt(tx)

    alice1_balance = web3.eth.getBalance(alice1)
    tx = policy_manager.transact({'from': alice1, 'gas_price': 0}) \
        .revokeArrangement(policy_id_2, ursula2)
    chain.wait_for_receipt(tx)
    assert 7000 == web3.eth.getBalance(policy_manager.address)
    assert alice1_balance + 1000 == web3.eth.getBalance(alice1)
    assert 0 == web3.toInt(
        policy_manager.call().getPolicyInfo(DISABLED_FIELD, policy_id_2, NULL_ADDR).encode('latin-1'))

    # Can't revoke again
    with pytest.raises(TransactionFailed):
        tx = policy_manager.transact({'from': alice1}).revokeArrangement(policy_id_2, ursula2)
        chain.wait_for_receipt(tx)

    # Wait, confirm activity, mint
    wait_time(chain, 1)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': ursula3}).confirmActivity()
    chain.wait_for_receipt(tx)

    wait_time(chain, 1)
    tx = policy_manager.transact({'from': alice2, 'gas_price': 0})\
        .revokeArrangement(policy_id_3, user_escrow_1.address)
    chain.wait_for_receipt(tx)

    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': ursula3}).confirmActivity()
    chain.wait_for_receipt(tx)

    wait_time(chain, 1)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)

    wait_time(chain, 1)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)

    # Withdraw reward and refund
    wait_time(chain, 3)
    ursula1_balance = web3.eth.getBalance(ursula1)
    tx = policy_manager.transact({'from': ursula1, 'gas_price': 0}).withdraw()
    chain.wait_for_receipt(tx)
    assert ursula1_balance < web3.eth.getBalance(ursula1)
    ursula2_balance = web3.eth.getBalance(ursula2)
    tx = policy_manager.transact({'from': ursula2, 'gas_price': 0}).withdraw()
    chain.wait_for_receipt(tx)
    assert ursula2_balance < web3.eth.getBalance(ursula2)
    user_escrow_1_balance = web3.eth.getBalance(user_escrow_1.address)
    tx = user_escrow_1.transact({'from': ursula3, 'gas_price': 0}).policyRewardWithdraw()
    chain.wait_for_receipt(tx)
    assert user_escrow_1_balance < web3.eth.getBalance(user_escrow_1.address)

    alice1_balance = web3.eth.getBalance(alice1)
    tx = policy_manager.transact({'from': alice1, 'gas_price': 0}).refund(policy_id_1)
    chain.wait_for_receipt(tx)
    assert alice1_balance < web3.eth.getBalance(alice1)
    alice1_balance = web3.eth.getBalance(alice1)
    tx = policy_manager.transact({'from': alice1, 'gas_price': 0}).refund(policy_id_2)
    chain.wait_for_receipt(tx)
    assert alice1_balance < web3.eth.getBalance(alice1)
    alice2_balance = web3.eth.getBalance(alice2)
    tx = policy_manager.transact({'from': alice2, 'gas_price': 0}).refund(policy_id_3)
    chain.wait_for_receipt(tx)
    assert alice2_balance == web3.eth.getBalance(alice2)
    tx = policy_manager.transact({'from': alice2, 'gas_price': 0}).refund(policy_id_4)
    chain.wait_for_receipt(tx)
    assert alice2_balance < web3.eth.getBalance(alice2)

    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).switchLock()
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': ursula3}).switchLock()
    chain.wait_for_receipt(tx)

    # Unlock and withdraw all tokens in MinersEscrow
    for index in range(9):
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait_for_receipt(tx)
        tx = escrow.transact({'from': ursula2}).confirmActivity()
        chain.wait_for_receipt(tx)
        tx = user_escrow_1.transact({'from': ursula3}).confirmActivity()
        chain.wait_for_receipt(tx)
        wait_time(chain, 1)

    wait_time(chain, 1)
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).mint()
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.transact({'from': ursula3}).mint()
    chain.wait_for_receipt(tx)

    assert 0 == escrow.call().getLockedTokens(ursula1)
    assert 0 == escrow.call().getLockedTokens(ursula2)
    assert 0 == escrow.call().getLockedTokens(ursula3)
    assert 0 == escrow.call().getLockedTokens(ursula4)
    assert 0 == escrow.call().getLockedTokens(user_escrow_1.address)
    assert 0 == escrow.call().getLockedTokens(user_escrow_2.address)

    tokens_amount = web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula1, 0).encode('latin-1'))
    tx = escrow.transact({'from': ursula1}).withdraw(tokens_amount)
    chain.wait_for_receipt(tx)
    tokens_amount = web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula2, 0).encode('latin-1'))
    tx = escrow.transact({'from': ursula2}).withdraw(tokens_amount)
    chain.wait_for_receipt(tx)
    tokens_amount = web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, user_escrow_1.address, 0).encode('latin-1'))
    tx = user_escrow_1.transact({'from': ursula3}).minerWithdraw(tokens_amount)
    chain.wait_for_receipt(tx)
    assert 10000 < token.call().balanceOf(ursula1)
    assert 1000 < token.call().balanceOf(ursula2)
    assert 10000 < token.call().balanceOf(user_escrow_1.address)

    # Unlock and withdraw all tokens in UserEscrow
    wait_time(chain, 1)
    assert 0 == user_escrow_1.call().getLockedTokens()
    assert 0 == user_escrow_2.call().getLockedTokens()
    tokens_amount = token.call().balanceOf(user_escrow_1.address)
    tx = user_escrow_1.transact({'from': ursula3}).withdraw(tokens_amount)
    chain.wait_for_receipt(tx)
    tokens_amount = token.call().balanceOf(user_escrow_2.address)
    tx = user_escrow_2.transact({'from': ursula4}).withdraw(tokens_amount)
    chain.wait_for_receipt(tx)
    assert 10000 < token.call().balanceOf(ursula3)
    assert 10000 == token.call().balanceOf(ursula4)
