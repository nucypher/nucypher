import pytest
from eth_tester.exceptions import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.deploy_contract('NuCypherKMSToken', int(2e9))
    return token


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    contract, _ = chain.provider.deploy_contract('MinersEscrowForUserEscrowMock', token.address)

    # Give escrow some coins
    tx = token.transact({'from': creator}).transfer(contract.address, 10000)
    chain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def policy_manager(chain):
    contract, _ = chain.provider.get_or_deploy_contract('PolicyManagerForUserEscrowMock')
    return contract


@pytest.fixture()
def user_escrow(web3, chain, token, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    # Creator deploys the user escrow
    contract, _ = chain.provider.deploy_contract('UserEscrow', token.address, escrow.address, policy_manager.address)

    # Transfer ownership
    tx = contract.transact({'from': creator}).transferOwnership(user)
    chain.wait_for_receipt(tx)
    return contract


def test_escrow(web3, chain, token, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]
    deposits = user_escrow.eventFilter('Deposited')

    # Deposit some tokens to the user escrow and lock them
    tx = token.transact({'from': creator}).approve(user_escrow.address, 2000)
    chain.wait_for_receipt(tx)
    tx = user_escrow.transact({'from': creator}).initialDeposit(1000, 1000)
    chain.wait_for_receipt(tx)
    assert 1000 == token.call().balanceOf(user_escrow.address)
    assert user == user_escrow.call().owner()
    assert 1000 >= user_escrow.call().getLockedTokens()
    assert 950 <= user_escrow.call().getLockedTokens()

    events = deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator == event_args['sender']
    assert 1000 == event_args['value']
    assert 1000 == event_args['duration']

    # Can't deposit tokens again
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator}).initialDeposit(1000, 1000)
        chain.wait_for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).withdraw(100)
        chain.wait_for_receipt(tx)

    # Can transfer more tokens
    tx = token.transact({'from': creator}).transfer(user_escrow.address, 1000)
    chain.wait_for_receipt(tx)
    assert 2000 == token.call().balanceOf(user_escrow.address)

    withdraws = user_escrow.eventFilter('Withdrawn')

    # Only user can withdraw available tokens
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator}).withdraw(100)
        chain.wait_for_receipt(tx)
    tx = user_escrow.transact({'from': user}).withdraw(1000)
    chain.wait_for_receipt(tx)
    assert 1000 == token.call().balanceOf(user)
    assert 1000 == token.call().balanceOf(user_escrow.address)

    events = withdraws.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']

    # Wait some time
    chain.wait_time(seconds=500)
    assert 500 >= user_escrow.call().getLockedTokens()
    assert 450 <= user_escrow.call().getLockedTokens()

    # User can withdraw some unlocked tokens
    tx = user_escrow.transact({'from': user}).withdraw(500)
    chain.wait_for_receipt(tx)
    assert 1500 == token.call().balanceOf(user)

    # events = user_escrow.pastEvents('Withdrawn').get()
    events = withdraws.get_all_entries()

    assert 2 == len(events)
    event_args = events[1]['args']
    assert user == event_args['owner']
    assert 500 == event_args['value']

    # Wait more time and withdraw all
    chain.wait_time(seconds=500)
    assert 0 == user_escrow.call().getLockedTokens()
    tx = user_escrow.transact({'from': user}).withdraw(500)
    chain.wait_for_receipt(tx)
    assert 0 == token.call().balanceOf(user_escrow.address)
    assert 2000 == token.call().balanceOf(user)

    # events = user_escrow.pastEvents('Withdrawn').get()
    events = withdraws.get_all_entries()

    assert 3 == len(events)
    event_args = events[2]['args']
    assert user == event_args['owner']
    assert 500 == event_args['value']


def test_miner(web3, chain, token, escrow, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    deposits = user_escrow.eventFilter('Deposited')

    # Deposit some tokens to the user escrow and lock them
    tx = token.transact({'from': creator}).approve(user_escrow.address, 1000)
    chain.wait_for_receipt(tx)
    tx = user_escrow.transact({'from': creator}).initialDeposit(1000, 1000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(user_escrow.address, 1000)
    chain.wait_for_receipt(tx)
    assert 2000 == token.call().balanceOf(user_escrow.address)

    events = deposits.get_all_entries()
    assert 1 == len(events)

    # Only user can deposit tokens to the miner escrow
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator}).minerDeposit(1000, 5)
        chain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).minerDeposit(10000, 5)
        chain.wait_for_receipt(tx)

    miner_deposits = user_escrow.eventFilter('DepositedAsMiner')

    # Deposit some tokens to the miners escrow
    tx = user_escrow.transact({'from': user}).minerDeposit(1500, 5)
    chain.wait_for_receipt(tx)
    assert user_escrow.address == escrow.call().node()
    assert 1500 == escrow.call().value()
    assert 1500 == escrow.call().lockedValue()
    assert 5 == escrow.call().periods()
    assert not escrow.call().unlock()
    assert 11500 == token.call().balanceOf(escrow.address)
    assert 500 == token.call().balanceOf(user_escrow.address)

    events = miner_deposits.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1500 == event_args['value']
    assert 5 == event_args['periods']

    # Can't withdraw because of locking
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).withdraw(100)
        chain.wait_for_receipt(tx)

    # Can't use the miners escrow directly
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).lock(100, 1)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).switchLock()
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).confirmActivity()
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).mint()
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).withdraw(100)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).withdrawAll()
        chain.wait_for_receipt(tx)

    locks = user_escrow.eventFilter('Locked')
    switches = user_escrow.eventFilter('LockSwitched')
    confirms = user_escrow.eventFilter('ActivityConfirmed')
    mints = user_escrow.eventFilter('Mined')
    miner_withdraws = user_escrow.eventFilter('WithdrawnAsMiner')
    withdraws = user_escrow.eventFilter('Withdrawn')


    # Use methods through the user escrow
    tx = user_escrow.transact({'from': user}).lock(100, 1)
    chain.wait_for_receipt(tx)
    assert 1500 == escrow.call().value()
    assert 1600 == escrow.call().lockedValue()
    assert 6 == escrow.call().periods()
    tx = user_escrow.transact({'from': user}).switchLock()
    chain.wait_for_receipt(tx)
    assert escrow.call().unlock()
    tx = user_escrow.transact({'from': user}).confirmActivity()
    chain.wait_for_receipt(tx)
    assert 1 == escrow.call().confirmedPeriod()
    tx = user_escrow.transact({'from': user}).mint()
    chain.wait_for_receipt(tx)
    assert 2500 == escrow.call().value()
    tx = user_escrow.transact({'from': user}).minerWithdraw(1500)
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.call().value()
    assert 10000 == token.call().balanceOf(escrow.address)
    assert 2000 == token.call().balanceOf(user_escrow.address)
    tx = user_escrow.transact({'from': user}).minerWithdraw(1000)
    chain.wait_for_receipt(tx)
    assert 0 == escrow.call().value()
    assert 9000 == token.call().balanceOf(escrow.address)
    assert 3000 == token.call().balanceOf(user_escrow.address)

    events = locks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 100 == event_args['value']
    assert 1 == event_args['periods']

    events = switches.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']

    events = confirms.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']

    events = mints.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']

    events = miner_withdraws.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1500 == event_args['value']
    event_args = events[1]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']

    # User can withdraw reward for mining but no more than locked
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).withdraw(2500)
        chain.wait_for_receipt(tx)
    tx = user_escrow.transact({'from': user}).withdraw(1000)
    chain.wait_for_receipt(tx)
    assert 2000 == token.call().balanceOf(user_escrow.address)
    assert 1000 == token.call().balanceOf(user)

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']


def test_policy(web3, chain, policy_manager, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]
    user_balance = web3.eth.getBalance(user)

    # Only user can withdraw reward
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator, 'gas_price': 0}).policyRewardWithdraw()
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator, 'gas_price': 0}).rewardWithdraw()
        chain.wait_for_receipt(tx)

    # Nothing to reward
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user, 'gas_price': 0}).policyRewardWithdraw()
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user, 'gas_price': 0}).rewardWithdraw()
        chain.wait_for_receipt(tx)
    assert user_balance == web3.eth.getBalance(user)
    assert 0 == web3.eth.getBalance(user_escrow.address)

    # Send ETH to the policy manager as a reward for the user
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': policy_manager.address, 'value': 10000})
    chain.wait_for_receipt(tx)

    miner_collections = user_escrow.eventFilter('RewardWithdrawnAsMiner')
    rewards = user_escrow.eventFilter('RewardWithdrawn')

    # Withdraw reward reward
    tx = user_escrow.transact({'from': user, 'gas_price': 0}).policyRewardWithdraw()
    chain.wait_for_receipt(tx)
    assert user_balance == web3.eth.getBalance(user)
    assert 10000 == web3.eth.getBalance(user_escrow.address)
    tx = user_escrow.transact({'from': user, 'gas_price': 0}).rewardWithdraw()
    chain.wait_for_receipt(tx)
    assert user_balance + 10000 == web3.eth.getBalance(user)
    assert 0 == web3.eth.getBalance(user_escrow.address)

    events = miner_collections.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 10000 == event_args['value']

    events = rewards.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 10000 == event_args['value']
