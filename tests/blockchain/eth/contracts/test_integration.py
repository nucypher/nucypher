import os

import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract



NULL_ADDR = '0x' + '0' * 40

VALUE_FIELD = 0
DECIMALS_FIELD = 1
CONFIRMED_PERIOD_1_FIELD = 2
CONFIRMED_PERIOD_2_FIELD = 3
LAST_ACTIVE_PERIOD_FIELD = 4

CLIENT_FIELD = 0
RATE_FIELD = 1
FIRST_REWARD_FIELD = 2
START_PERIOD_FIELD = 3
LAST_PERIOD_FIELD = 4
DISABLED_FIELD = 5

REWARD_FIELD = 0
REWARD_RATE_FIELD = 1
LAST_MINED_PERIOD_FIELD = 2

ACTIVE_STATE = 0
UPGRADE_WAITING_STATE = 1
FINISHED_STATE = 2

UPGRADE_GOVERNMENT = 0
UPGRADE_ESCROW = 1
UPGRADE_POLICY_MANAGER = 2
ROLLBACK_GOVERNMENT = 3
ROLLBACK_ESCROW = 4
ROLLBACK_POLICY_MANAGER = 5


@pytest.fixture()
def token(chain):
    # Create an ERC20 token
    contract, _ = chain.provider.deploy_contract('NuCypherToken', 2 * 10 ** 9)
    return contract


@pytest.fixture()
def escrow(web3, chain, token):
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

    # Wrap dispatcher contract
    contract = web3.eth.contract(abi=contract.abi, address=dispatcher.address, ContractFactoryClass=Contract)
    return contract


@pytest.fixture()
def policy_manager(web3, chain, escrow):
    creator = web3.eth.accounts[0]

    # Creator deploys the policy manager
    contract, _ = chain.provider.deploy_contract('PolicyManager', escrow.address)
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

    # Wrap dispatcher contract
    contract = web3.eth.contract(abi=contract.abi, address=dispatcher.address, ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def government(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]

    # Creator deploys the government
    contract, _ = chain.provider.deploy_contract('Government', escrow.address, policy_manager.address, 1)
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

    # Wrap dispatcher contract
    contract = web3.eth.contract(abi=contract.abi, address=dispatcher.address, ContractFactoryClass=Contract)

    # Transfer ownership
    tx = contract.functions.transferOwnership(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.transferOwnership(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = policy_manager.functions.transferOwnership(contract.address).transact({'from': creator})
    chain.wait_for_receipt(tx)

    return contract


@pytest.mark.slow
def test_all(web3, chain, token, escrow, policy_manager, government):
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
    user_escrow_1, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address, government.address)
    tx = user_escrow_1.functions.transferOwnership(ursula3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.approve(user_escrow_1.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.initialDeposit(10000, 20 * 60 * 60).transact({'from': creator})
    chain.wait_for_receipt(tx)
    user_escrow_2, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address, government.address)
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
    tx = escrow.functions.preDeposit([ursula2], [1000], [9]).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert reward + 1000 == token.functions.balanceOf(escrow.address).call()
    assert 1000 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 9).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 10).call()

    # Can't pre-deposit tokens again for the same owner
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula2], [1000], [9]).transact({'from': creator})
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
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 10).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 11).call()

    # Wait 1 period and deposit from one more Ursula
    chain.time_travel(hours=1)
    tx = user_escrow_1.functions.minerDeposit(1000, 10).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.minerInfo(user_escrow_1.address).call()[VALUE_FIELD]
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 1000 == escrow.functions.getLockedTokens(user_escrow_1.address, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(user_escrow_1.address, 10).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address, 11).call()
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

    # Divide stakes
    tx = escrow.functions.divideStake(1000, escrow.functions.getCurrentPeriod().call() + 9, 500, 6).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.divideStake(1000, escrow.functions.getCurrentPeriod().call() + 9, 500, 9).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.divideStake(1000, escrow.functions.getCurrentPeriod().call() + 10, 500, 6).transact({'from': ursula3})
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
    tx = policy_manager.functions.createPolicy(policy_id_1, 5, 44, [ursula1, ursula2]).transact({'from': alice1, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_2 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_2, 5, 44, [ursula2, user_escrow_1.address]).transact({'from': alice1, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_3 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_3, 5, 44, [ursula1, user_escrow_1.address]).transact({'from': alice2, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_4 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_4, 5, 44, [ursula2, user_escrow_1.address]).transact({'from': alice2, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    chain.wait_for_receipt(tx)
    policy_id_5 = os.urandom(20)
    tx = policy_manager.functions.createPolicy(policy_id_5, 5, 44, [ursula1, ursula2]).transact({'from': alice2, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    chain.wait_for_receipt(tx)

    # Only Alice can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    alice2_balance = web3.eth.getBalance(alice2)
    tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice2, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert 8440 == web3.eth.getBalance(policy_manager.address)
    assert alice2_balance + 2000 == web3.eth.getBalance(alice2)
    assert policy_manager.functions.policies(policy_id_5).call()[DISABLED_FIELD]

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
    assert 7440 == web3.eth.getBalance(policy_manager.address)
    assert alice1_balance + 1000 == web3.eth.getBalance(alice1)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

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

    # Voting for upgrade
    escrow_v1 = escrow.functions.target().call()
    policy_manager_v1 = policy_manager.functions.target().call()
    government_v1 = government.functions.target().call()
    # Creator deploys the contracts as the second versions
    escrow_v2, _ = chain.provider.deploy_contract(
        'MinersEscrow',
        token.address,
        1,
        4 * 2 * 10 ** 7,
        4,
        4,
        2,
        100,
        2000)
    policy_manager_v2, _ = chain.provider.deploy_contract('PolicyManager', escrow.address)
    government_v2, _ = chain.provider.deploy_contract('Government', escrow.address, policy_manager.address, 1)
    assert FINISHED_STATE == government.functions.getVotingState().call()

    # Alice can't create voting
    with pytest.raises((TransactionFailed, ValueError)):
        tx = government.functions.createVoting(UPGRADE_GOVERNMENT, government_v2.address).transact({'from': alice1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = government.functions.createVoting(UPGRADE_GOVERNMENT, government_v2.address).transact({'from': alice2})
        chain.wait_for_receipt(tx)

    # Vote and upgrade government contract
    tx = government.functions.createVoting(UPGRADE_GOVERNMENT, government_v2.address).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert ACTIVE_STATE == government.functions.getVotingState().call()
    # Alice can't vote
    with pytest.raises((TransactionFailed, ValueError)):
        tx = government.functions.vote(False).transact({'from': alice1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = government.functions.vote(False).transact({'from': alice2})
        chain.wait_for_receipt(tx)

    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(False).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.vote(True).transact({'from': ursula3})
    chain.wait_for_receipt(tx)

    # Can't vote again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = government.functions.vote(False).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    chain.time_travel(1)
    assert UPGRADE_WAITING_STATE == government.functions.getVotingState().call()
    tx = government.functions.commitUpgrade().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert government_v2.address == government.functions.target().call()

    # Vote and upgrade escrow contract
    tx = government.functions.createVoting(UPGRADE_ESCROW, escrow_v2.address).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert ACTIVE_STATE == government.functions.getVotingState().call()
    tx = government.functions.vote(False).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(True).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.vote(True).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    chain.time_travel(1)
    assert UPGRADE_WAITING_STATE == government.functions.getVotingState().call()
    tx = government.functions.commitUpgrade().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert escrow_v2.address == escrow.functions.target().call()

    # Vote and upgrade policy manager contract
    tx = government.functions.createVoting(UPGRADE_POLICY_MANAGER, policy_manager_v2.address).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert ACTIVE_STATE == government.functions.getVotingState().call()
    tx = government.functions.vote(False).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(True).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.vote(True).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    chain.time_travel(1)
    assert UPGRADE_WAITING_STATE == government.functions.getVotingState().call()
    tx = government.functions.commitUpgrade().transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert policy_manager_v2.address == policy_manager.functions.target().call()

    # Voting against rollback
    tx = government.functions.createVoting(ROLLBACK_GOVERNMENT, NULL_ADDR).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert ACTIVE_STATE == government.functions.getVotingState().call()
    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.vote(False).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    chain.time_travel(1)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert government_v2.address == government.functions.target().call()

    tx = government.functions.createVoting(ROLLBACK_ESCROW, NULL_ADDR).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert ACTIVE_STATE == government.functions.getVotingState().call()
    tx = government.functions.vote(True).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.vote(False).transact({'from': ursula3})
    chain.wait_for_receipt(tx)
    chain.time_travel(1)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert escrow_v2.address == escrow.functions.target().call()

    tx = government.functions.createVoting(ROLLBACK_ESCROW, NULL_ADDR).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert ACTIVE_STATE == government.functions.getVotingState().call()
    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(False).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    chain.time_travel(1)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert policy_manager_v2.address == policy_manager.functions.target().call()

    # Voting for upgrade with errors
    tx = government.functions.createVoting(UPGRADE_GOVERNMENT, escrow_v2.address).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    chain.time_travel(1)
    assert UPGRADE_WAITING_STATE == government.functions.getVotingState().call()
    tx = government.functions.commitUpgrade().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert FINISHED_STATE == government.functions.getVotingState().call()
    assert government_v2.address == government.functions.target().call()

    # Some activity
    for index in range(5):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)
        tx = escrow.functions.confirmActivity().transact({'from': ursula2})
        chain.wait_for_receipt(tx)
        tx = user_escrow_1.functions.confirmActivity().transact({'from': ursula3})
        chain.wait_for_receipt(tx)
        chain.time_travel(hours=1)

    # Vote and rollback all contracts
    tx = government.functions.createVoting(ROLLBACK_GOVERNMENT, NULL_ADDR).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    tx = government.functions.commitUpgrade().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert government_v1 == government.functions.target().call()

    tx = government.functions.createVoting(ROLLBACK_ESCROW, NULL_ADDR).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    tx = government.functions.commitUpgrade().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert escrow_v1 == escrow.functions.target().call()

    tx = government.functions.createVoting(ROLLBACK_POLICY_MANAGER, NULL_ADDR).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = government.functions.vote(True).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    tx = government.functions.commitUpgrade().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert policy_manager_v1 == policy_manager.functions.target().call()

    # Unlock and withdraw all tokens in MinersEscrow
    for index in range(6):
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

    tokens_amount = escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tokens_amount = escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tokens_amount = escrow.functions.minerInfo(user_escrow_1.address).call()[VALUE_FIELD]
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
