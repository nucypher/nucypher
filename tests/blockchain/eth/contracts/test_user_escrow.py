import pytest
from eth_tester.exceptions import TransactionFailed


@pytest.fixture()
def token(chain):
    # Create an ERC20 token
    token, _ = chain.provider.deploy_contract('NuCypherToken', int(2e9))
    return token


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    contract, _ = chain.provider.deploy_contract('MinersEscrowForUserEscrowMock', token.address)

    # Give escrow some coins
    tx = token.functions.transfer(contract.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def policy_manager(chain):
    contract, _ = chain.provider.deploy_contract('PolicyManagerForUserEscrowMock')
    return contract


@pytest.fixture()
def government(chain):
    contract, _ = chain.provider.deploy_contract('GovernmentForUserEscrowMock')
    return contract


@pytest.fixture()
def user_escrow(web3, chain, token, escrow, policy_manager, government):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    # Creator deploys the user escrow
    contract, _ = chain.provider.deploy_contract(
        'UserEscrow', token.address, escrow.address, policy_manager.address, government.address)

    # Transfer ownership
    tx = contract.functions.transferOwnership(user).transact({'from': creator})
    chain.wait_for_receipt(tx)
    return contract


@pytest.mark.slow
def test_escrow(web3, chain, token, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]
    deposits = user_escrow.events.Deposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the user escrow and lock them
    tx = token.functions.approve(user_escrow.address, 2000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(user_escrow.address).call()
    assert user == user_escrow.functions.owner().call()
    assert 1000 >= user_escrow.functions.getLockedTokens().call()
    assert 950 <= user_escrow.functions.getLockedTokens().call()

    events = deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator == event_args['sender']
    assert 1000 == event_args['value']
    assert 1000 == event_args['duration']

    # Can't deposit tokens again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdraw(100).transact({'from': user})
        chain.wait_for_receipt(tx)

    # Can transfer more tokens
    tx = token.functions.transfer(user_escrow.address, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()

    withdraws = user_escrow.events.Withdrawn.createFilter(fromBlock='latest')

    # Only user can withdraw available tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdraw(100).transact({'from': creator})
        chain.wait_for_receipt(tx)
    tx = user_escrow.functions.withdraw(1000).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(user).call()
    assert 1000 == token.functions.balanceOf(user_escrow.address).call()

    events = withdraws.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']

    # Wait some time
    chain.time_travel(seconds=500)
    assert 500 >= user_escrow.functions.getLockedTokens().call()
    assert 450 <= user_escrow.functions.getLockedTokens().call()

    # User can withdraw some unlocked tokens
    tx = user_escrow.functions.withdraw(500).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(user).call()

    # events = user_escrow.pastEvents('Withdrawn').get()
    events = withdraws.get_all_entries()

    assert 2 == len(events)
    event_args = events[1]['args']
    assert user == event_args['owner']
    assert 500 == event_args['value']

    # Wait more time and withdraw all
    chain.time_travel(seconds=500)
    assert 0 == user_escrow.functions.getLockedTokens().call()
    tx = user_escrow.functions.withdraw(500).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 0 == token.functions.balanceOf(user_escrow.address).call()
    assert 2000 == token.functions.balanceOf(user).call()

    # events = user_escrow.pastEvents('Withdrawn').get()
    events = withdraws.get_all_entries()

    assert 3 == len(events)
    event_args = events[2]['args']
    assert user == event_args['owner']
    assert 500 == event_args['value']


@pytest.mark.slow
def test_miner(web3, chain, token, escrow, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]

    deposits = user_escrow.events.Deposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the user escrow and lock them
    tx = token.functions.approve(user_escrow.address, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(user_escrow.address, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()

    events = deposits.get_all_entries()
    assert 1 == len(events)

    # Only user can deposit tokens to the miner escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.minerDeposit(1000, 5).transact({'from': creator})
        chain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.minerDeposit(10000, 5).transact({'from': user})
        chain.wait_for_receipt(tx)

    miner_deposits = user_escrow.events.DepositedAsMiner.createFilter(fromBlock='latest')

    # Deposit some tokens to the miners escrow
    tx = user_escrow.functions.minerDeposit(1500, 5).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert user_escrow.address == escrow.functions.node().call()
    assert 1500 == escrow.functions.value().call()
    assert 1500 == escrow.functions.lockedValue().call()
    assert 5 == escrow.functions.periods().call()
    assert 11500 == token.functions.balanceOf(escrow.address).call()
    assert 500 == token.functions.balanceOf(user_escrow.address).call()

    events = miner_deposits.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1500 == event_args['value']
    assert 5 == event_args['periods']

    # Can't withdraw because of locking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdraw(100).transact({'from': user})
        chain.wait_for_receipt(tx)

    # Can't use the miners escrow directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(100, 1).transact({'from': user})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(1500, 5, 100, 1).transact({'from': user})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': user})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.mint().transact({'from': user})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': user})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdrawAll().transact({'from': user})
        chain.wait_for_receipt(tx)

    locks = user_escrow.events.Locked.createFilter(fromBlock='latest')
    divides = user_escrow.events.Divided.createFilter(fromBlock='latest')
    confirms = user_escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    mints = user_escrow.events.Mined.createFilter(fromBlock='latest')
    miner_withdraws = user_escrow.events.WithdrawnAsMiner.createFilter(fromBlock='latest')
    withdraws = user_escrow.events.Withdrawn.createFilter(fromBlock='latest')

    # Use methods through the user escrow
    tx = user_escrow.functions.lock(100, 1).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 1500 == escrow.functions.value().call()
    assert 1600 == escrow.functions.lockedValue().call()
    assert 6 == escrow.functions.periods().call()
    tx = user_escrow.functions.divideStake(1600, 6, 100, 1).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 1500 == escrow.functions.value().call()
    assert 1700 == escrow.functions.lockedValue().call()
    assert 7 == escrow.functions.periods().call()
    tx = user_escrow.functions.confirmActivity().transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 1 == escrow.functions.confirmedPeriod().call()
    tx = user_escrow.functions.mint().transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 2500 == escrow.functions.value().call()
    tx = user_escrow.functions.minerWithdraw(1500).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.value().call()
    assert 10000 == token.functions.balanceOf(escrow.address).call()
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()
    tx = user_escrow.functions.minerWithdraw(1000).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 0 == escrow.functions.value().call()
    assert 9000 == token.functions.balanceOf(escrow.address).call()
    assert 3000 == token.functions.balanceOf(user_escrow.address).call()

    events = locks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 100 == event_args['value']
    assert 1 == event_args['periods']

    events = divides.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1600 == event_args['oldValue']
    assert 100 == event_args['newValue']
    assert 6 == event_args['lastPeriod']
    assert 1 == event_args['periods']

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
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdraw(2500).transact({'from': user})
        chain.wait_for_receipt(tx)
    tx = user_escrow.functions.withdraw(1000).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()
    assert 1000 == token.functions.balanceOf(user).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']


@pytest.mark.slow
def test_policy(web3, chain, policy_manager, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]
    user_balance = web3.eth.getBalance(user)

    # Only user can withdraw reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.policyRewardWithdraw().transact({'from': creator, 'gas_price': 0})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.rewardWithdraw().transact({'from': creator, 'gas_price': 0})
        chain.wait_for_receipt(tx)

    # Nothing to reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.policyRewardWithdraw().transact({'from': user, 'gas_price': 0})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.rewardWithdraw().transact({'from': user, 'gas_price': 0})
        chain.wait_for_receipt(tx)
    assert user_balance == web3.eth.getBalance(user)
    assert 0 == web3.eth.getBalance(user_escrow.address)

    # Send ETH to the policy manager as a reward for the user
    tx = web3.eth.sendTransaction({'from': web3.eth.coinbase, 'to': policy_manager.address, 'value': 10000})
    chain.wait_for_receipt(tx)

    miner_collections = user_escrow.events.RewardWithdrawnAsMiner.createFilter(fromBlock='latest')
    rewards = user_escrow.events.RewardWithdrawn.createFilter(fromBlock='latest')

    # Withdraw reward reward
    tx = user_escrow.functions.policyRewardWithdraw().transact({'from': user, 'gas_price': 0})
    chain.wait_for_receipt(tx)
    assert user_balance == web3.eth.getBalance(user)
    assert 10000 == web3.eth.getBalance(user_escrow.address)
    tx = user_escrow.functions.rewardWithdraw().transact({'from': user, 'gas_price': 0})
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

    # Set min reward rate
    min_reward_sets = user_escrow.events.MinRewardRateSet.createFilter(fromBlock='latest')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.setMinRewardRate(333).transact({'from': creator})
        chain.wait_for_receipt(tx)
    tx = user_escrow.functions.setMinRewardRate(222).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert 222 == policy_manager.functions.minRewardRate().call()

    events = min_reward_sets.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 222 == event_args['value']


@pytest.mark.slow
def test_government(web3, chain, government, user_escrow):
    creator = web3.eth.accounts[0]
    user = web3.eth.accounts[1]
    votes = user_escrow.events.Voted.createFilter(fromBlock='latest')

    # Only user can vote
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.vote(True).transact({'from': creator})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.vote(False).transact({'from': creator})
        chain.wait_for_receipt(tx)

    tx = user_escrow.functions.vote(True).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert government.functions.voteFor().call()
    tx = user_escrow.functions.vote(False).transact({'from': user})
    chain.wait_for_receipt(tx)
    assert not government.functions.voteFor().call()

    events = votes.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert event_args['voteFor']
    event_args = events[1]['args']
    assert user == event_args['owner']
    assert not event_args['voteFor']
