import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.get_or_deploy_contract(
        'NuCypherKMSToken', deploy_args=[2 * 10 ** 9],
        deploy_transaction={'from': creator})
    return token


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    escrow, _ = chain.provider.get_or_deploy_contract(
        'MinersEscrowForUserEscrowMock', deploy_args=[token.address],
        deploy_transaction={'from': creator})

    # Give escrow some coins
    tx = token.transact({'from': creator}).transfer(escrow.address, 10000)
    chain.wait.for_receipt(tx)

    return escrow


@pytest.fixture()
def user_escrow(web3, chain, token, escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    # Creator deploys the user escrow
    user_escrow, _ = chain.provider.get_or_deploy_contract(
        'UserEscrow', deploy_args=[token.address, escrow.address],
        deploy_transaction={'from': creator})

    # Transfer ownership
    tx = user_escrow.transact({'from': creator}).transferOwnership(user)
    chain.wait.for_receipt(tx)
    return user_escrow


def wait_time(chain, wait_seconds):
    web3 = chain.web3
    step = 1
    end_timestamp = web3.eth.getBlock(web3.eth.blockNumber).timestamp + wait_seconds
    while web3.eth.getBlock(web3.eth.blockNumber).timestamp < end_timestamp:
        chain.wait.for_block(web3.eth.blockNumber + step)


def test_escrow(web3, chain, token, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    # Deposit some tokens to the user escrow and lock them
    tx = token.transact({'from': creator}).approve(user_escrow.address, 2000)
    chain.wait.for_receipt(tx)
    tx = user_escrow.transact({'from': creator}).initialDeposit(1000, 1000)
    chain.wait.for_receipt(tx)
    assert 1000 == token.call().balanceOf(user_escrow.address)
    assert user == user_escrow.call().owner()
    assert 1000 >= user_escrow.call().getLockedTokens()
    assert 950 <= user_escrow.call().getLockedTokens()

    events = user_escrow.pastEvents('Deposited').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator.lower() == event_args['sender'].lower()
    assert 1000 == event_args['value']
    assert 1000 == event_args['duration']

    # Can't deposit tokens again
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator}).initialDeposit(1000, 1000)
        chain.wait.for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).withdraw(100)
        chain.wait.for_receipt(tx)

    # Can transfer more tokens
    tx = token.transact({'from': creator}).transfer(user_escrow.address, 1000)
    chain.wait.for_receipt(tx)
    assert 2000 == token.call().balanceOf(user_escrow.address)

    # Only user can withdraw available tokens
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator}).withdraw(100)
        chain.wait.for_receipt(tx)
    tx = user_escrow.transact({'from': user}).withdraw(1000)
    chain.wait.for_receipt(tx)
    assert 1000 == token.call().balanceOf(user)
    assert 1000 == token.call().balanceOf(user_escrow.address)

    events = user_escrow.pastEvents('Withdrawn').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 1000 == event_args['value']

    # Wait some time
    wait_time(chain, 500)
    assert 500 >= user_escrow.call().getLockedTokens()
    assert 450 <= user_escrow.call().getLockedTokens()

    # User can withdraw some unlocked tokens
    tx = user_escrow.transact({'from': user}).withdraw(500)
    chain.wait.for_receipt(tx)
    assert 1500 == token.call().balanceOf(user)

    events = user_escrow.pastEvents('Withdrawn').get()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 500 == event_args['value']

    # Wait more time and withdraw all
    wait_time(chain, 500)
    assert 0 == user_escrow.call().getLockedTokens()
    tx = user_escrow.transact({'from': user}).withdraw(500)
    chain.wait.for_receipt(tx)
    assert 0 == token.call().balanceOf(user_escrow.address)
    assert 2000 == token.call().balanceOf(user)

    events = user_escrow.pastEvents('Withdrawn').get()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 500 == event_args['value']


def test_miner(web3, chain, token, escrow, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    # Deposit some tokens to the user escrow and lock them
    tx = token.transact({'from': creator}).approve(user_escrow.address, 1000)
    chain.wait.for_receipt(tx)
    tx = user_escrow.transact({'from': creator}).initialDeposit(1000, 1000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(user_escrow.address, 1000)
    chain.wait.for_receipt(tx)
    assert 2000 == token.call().balanceOf(user_escrow.address)
    assert 1 == len(user_escrow.pastEvents('Deposited').get())

    # Only user can deposit tokens to the miner escrow
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': creator}).minerDeposit(1000, 5)
        chain.wait.for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).minerDeposit(10000, 5)
        chain.wait.for_receipt(tx)

    # Deposit some tokens to the miners escrow
    tx = user_escrow.transact({'from': user}).minerDeposit(1500, 5)
    chain.wait.for_receipt(tx)
    assert user_escrow.address.lower() == escrow.call().node().lower()
    assert 1500 == escrow.call().value()
    assert 1500 == escrow.call().lockedValue()
    assert 5 == escrow.call().periods()
    assert not escrow.call().unlock()
    assert 11500 == token.call().balanceOf(escrow.address)
    assert 500 == token.call().balanceOf(user_escrow.address)

    events = user_escrow.pastEvents('DepositedAsMiner').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 1500 == event_args['value']
    assert 5 == event_args['periods']

    # Can't withdraw because of locking
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).withdraw(100)
        chain.wait.for_receipt(tx)

    # Can't use the miners escrow directly
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).lock(100, 1)
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).switchLock()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).confirmActivity()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).mint()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).withdraw(100)
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': user}).withdrawAll()
        chain.wait.for_receipt(tx)

    # Use methods through the user escrow
    tx = user_escrow.transact({'from': user}).lock(100, 1)
    chain.wait.for_receipt(tx)
    assert 1500 == escrow.call().value()
    assert 1600 == escrow.call().lockedValue()
    assert 6 == escrow.call().periods()
    tx = user_escrow.transact({'from': user}).switchLock()
    chain.wait.for_receipt(tx)
    assert escrow.call().unlock()
    tx = user_escrow.transact({'from': user}).confirmActivity()
    chain.wait.for_receipt(tx)
    assert 1 == escrow.call().confirmedPeriod()
    tx = user_escrow.transact({'from': user}).mint()
    chain.wait.for_receipt(tx)
    assert 2500 == escrow.call().value()
    tx = user_escrow.transact({'from': user}).minerWithdraw(1500)
    chain.wait.for_receipt(tx)
    assert 1000 == escrow.call().value()
    assert 10000 == token.call().balanceOf(escrow.address)
    assert 2000 == token.call().balanceOf(user_escrow.address)
    tx = user_escrow.transact({'from': user}).minerWithdrawAll()
    chain.wait.for_receipt(tx)
    assert 0 == escrow.call().value()
    assert 9000 == token.call().balanceOf(escrow.address)
    assert 3000 == token.call().balanceOf(user_escrow.address)

    events = user_escrow.pastEvents('Locked').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 100 == event_args['value']
    assert 1 == event_args['periods']
    events = user_escrow.pastEvents('LockSwitched').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    events = user_escrow.pastEvents('ActivityConfirmed').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    events = user_escrow.pastEvents('Mined').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    events = user_escrow.pastEvents('WithdrawnAsMiner').get()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 1500 == event_args['value']
    event_args = events[1]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 1000 == event_args['value']

    # User can withdraw reward for mining but no more than locked
    with pytest.raises(TransactionFailed):
        tx = user_escrow.transact({'from': user}).withdraw(2500)
        chain.wait.for_receipt(tx)
    tx = user_escrow.transact({'from': user}).withdraw(1000)
    chain.wait.for_receipt(tx)
    assert 2000 == token.call().balanceOf(user_escrow.address)
    assert 1000 == token.call().balanceOf(user)

    events = user_escrow.pastEvents('Withdrawn').get()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user.lower() == event_args['owner'].lower()
    assert 1000 == event_args['value']
