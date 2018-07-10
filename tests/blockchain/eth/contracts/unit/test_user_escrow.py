import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract


@pytest.fixture()
def token(testerchain):
    # Create an ERC20 token
    token, _ = testerchain.interface.deploy_contract('NuCypherToken', int(2e9))
    return token


@pytest.fixture()
def escrow(testerchain, token):
    creator = testerchain.interface.w3.eth.accounts[0]
    # Creator deploys the escrow
    contract, _ = testerchain.interface.deploy_contract('MinersEscrowForUserEscrowMock', token.address)

    # Give some coins to the escrow
    tx = token.functions.transfer(contract.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def policy_manager(testerchain):
    contract, _ = testerchain.interface.deploy_contract('PolicyManagerForUserEscrowMock')
    return contract


@pytest.fixture()
def government(testerchain):
    contract, _ = testerchain.interface.deploy_contract('GovernmentForUserEscrowMock')
    return contract


@pytest.fixture()
def proxy(testerchain, token, escrow, policy_manager, government):
    # Creator deploys the user escrow proxy
    contract, _ = testerchain.interface.deploy_contract(
        'UserEscrowProxy', token.address, escrow.address, policy_manager.address, government.address)
    return contract


@pytest.fixture()
def linker(testerchain, proxy):
    linker, _ = testerchain.interface.deploy_contract('UserEscrowLibraryLinker', proxy.address)
    return linker


@pytest.fixture()
def user_escrow(testerchain, token, linker):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]

    contract, _ = testerchain.interface.deploy_contract('UserEscrow', linker.address, token.address)

    # Transfer ownership
    tx = contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


@pytest.fixture()
def user_escrow_proxy(testerchain, proxy, user_escrow):
    return testerchain.interface.w3.eth.contract(
        abi=proxy.abi,
        address=user_escrow.address,
        ContractFactoryClass=Contract)


@pytest.mark.slow
def test_escrow(testerchain, token, user_escrow):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]
    deposits = user_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the user escrow and lock them
    tx = token.functions.approve(user_escrow.address, 2000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
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
        testerchain.wait_for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # Can transfer more tokens
    tx = token.functions.transfer(user_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()

    withdraws = user_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')

    # Only user can withdraw available tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = user_escrow.functions.withdrawTokens(1000).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(user).call()
    assert 1000 == token.functions.balanceOf(user_escrow.address).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']

    # Wait some time
    testerchain.time_travel(seconds=500)
    assert 1000 == user_escrow.functions.getLockedTokens().call()

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(user).call()

    # Wait more time and withdraw all
    testerchain.time_travel(seconds=500)
    assert 0 == user_escrow.functions.getLockedTokens().call()
    tx = user_escrow.functions.withdrawTokens(1000).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 0 == token.functions.balanceOf(user_escrow.address).call()
    assert 2000 == token.functions.balanceOf(user).call()

    events = withdraws.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']


# TODO test state of the proxy contract
@pytest.mark.slow
def test_miner(testerchain, token, escrow, user_escrow, user_escrow_proxy):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]

    deposits = user_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the user escrow and lock them
    tx = token.functions.approve(user_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(user_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()

    events = deposits.get_all_entries()
    assert 1 == len(events)

    # Only user can deposit tokens to the miner escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.depositAsMiner(1000, 5).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.depositAsMiner(10000, 5).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    miner_deposits = user_escrow_proxy.events.DepositedAsMiner.createFilter(fromBlock='latest')

    # Deposit some tokens to the miners escrow
    tx = user_escrow_proxy.functions.depositAsMiner(1500, 5).transact({'from': user})
    testerchain.wait_for_receipt(tx)
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
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # Can't use the miners escrow directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(100, 1).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(1, 100, 1).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.mint().transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdrawAll().transact({'from': user})
        testerchain.wait_for_receipt(tx)

    locks = user_escrow_proxy.events.Locked.createFilter(fromBlock='latest')
    divides = user_escrow_proxy.events.Divided.createFilter(fromBlock='latest')
    confirms = user_escrow_proxy.events.ActivityConfirmed.createFilter(fromBlock='latest')
    mints = user_escrow_proxy.events.Mined.createFilter(fromBlock='latest')
    miner_withdraws = user_escrow_proxy.events.WithdrawnAsMiner.createFilter(fromBlock='latest')
    withdraws = user_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')

    # Use methods through the user escrow
    tx = user_escrow_proxy.functions.lock(100, 1).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 1500 == escrow.functions.value().call()
    assert 1600 == escrow.functions.lockedValue().call()
    assert 6 == escrow.functions.periods().call()
    tx = user_escrow_proxy.functions.divideStake(1, 100, 1).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 1500 == escrow.functions.value().call()
    assert 1700 == escrow.functions.lockedValue().call()
    assert 1 == escrow.functions.index().call()
    tx = user_escrow_proxy.functions.confirmActivity().transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 1 == escrow.functions.confirmedPeriod().call()
    tx = user_escrow_proxy.functions.mint().transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 2500 == escrow.functions.value().call()
    tx = user_escrow_proxy.functions.withdrawAsMiner(1500).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.value().call()
    assert 10000 == token.functions.balanceOf(escrow.address).call()
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()
    tx = user_escrow_proxy.functions.withdrawAsMiner(1000).transact({'from': user})
    testerchain.wait_for_receipt(tx)
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
    assert 1 == event_args['index']
    assert 100 == event_args['newValue']
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
        tx = user_escrow.functions.withdrawTokens(2500).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    tx = user_escrow.functions.withdrawTokens(1000).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()
    assert 1000 == token.functions.balanceOf(user).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1000 == event_args['value']


@pytest.mark.slow
def test_policy(testerchain, policy_manager, user_escrow, user_escrow_proxy):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]
    user_balance = testerchain.interface.w3.eth.getBalance(user)

    # Only user can withdraw reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.withdrawPolicyReward().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawETH().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Nothing to reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.withdrawPolicyReward().transact({'from': user, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawETH().transact({'from': user, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert user_balance == testerchain.interface.w3.eth.getBalance(user)
    assert 0 == testerchain.interface.w3.eth.getBalance(user_escrow.address)

    # Send ETH to the policy manager as a reward for the user
    tx = testerchain.interface.w3.eth.sendTransaction(
        {'from': testerchain.interface.w3.eth.coinbase, 'to': policy_manager.address, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    miner_reward = user_escrow_proxy.events.PolicyRewardWithdrawn.createFilter(fromBlock='latest')
    rewards = user_escrow.events.ETHWithdrawn.createFilter(fromBlock='latest')

    # Withdraw reward
    tx = user_escrow_proxy.functions.withdrawPolicyReward().transact({'from': user, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert user_balance + 10000 == testerchain.interface.w3.eth.getBalance(user)
    assert 0 == testerchain.interface.w3.eth.getBalance(policy_manager.address)
    assert 0 == testerchain.interface.w3.eth.getBalance(user_escrow.address)

    events = miner_reward.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 10000 == event_args['value']

    events = rewards.get_all_entries()
    assert 0 == len(events)

    # Set min reward rate
    min_reward_sets = user_escrow_proxy.events.MinRewardRateSet.createFilter(fromBlock='latest')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.setMinRewardRate(333).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = user_escrow_proxy.functions.setMinRewardRate(222).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 222 == policy_manager.functions.minRewardRate().call()

    events = min_reward_sets.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 222 == event_args['value']


@pytest.mark.slow
def test_government(testerchain, government, user_escrow_proxy):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]
    votes = user_escrow_proxy.events.Voted.createFilter(fromBlock='latest')

    # Only user can vote
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.vote(True).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.vote(False).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    tx = user_escrow_proxy.functions.vote(True).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert government.functions.voteFor().call()
    tx = user_escrow_proxy.functions.vote(False).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert not government.functions.voteFor().call()

    events = votes.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert event_args['voteFor']
    event_args = events[1]['args']
    assert user == event_args['owner']
    assert not event_args['voteFor']


@pytest.mark.slow
def test_library(testerchain, government, user_escrow_proxy):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]
    tx = testerchain.interface.w3.eth.sendTransaction(
        {'from': testerchain.interface.w3.eth.coinbase, 'to': user, 'value': 1})
    testerchain.wait_for_receipt(tx)

    # Create fake instance of the user escrow contract
    fake_user_escrow = testerchain.interface.w3.eth.contract(
        abi=government.abi,
        address=user_escrow_proxy.address,
        ContractFactoryClass=Contract)

    # Can't execute method that not in the proxy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = fake_user_escrow.functions.vote(False).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # And can't send ETH to the user escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.interface.w3.eth.sendTransaction(
            {'from': user, 'to': user_escrow_proxy.address, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


@pytest.mark.slow
def test_library(testerchain, token):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]
    tx = testerchain.interface.w3.eth.sendTransaction(
        {'from': testerchain.interface.w3.eth.coinbase, 'to': user, 'value': 1})
    testerchain.wait_for_receipt(tx)

    library_v1, _ = testerchain.interface.deploy_contract('UserEscrowLibraryMockV1')
    library_v2, _ = testerchain.interface.deploy_contract('UserEscrowLibraryMockV2')
    linker_contract, _ = testerchain.interface.deploy_contract('UserEscrowLibraryLinker', library_v1.address)
    user_escrow_contract, _ = testerchain.interface.deploy_contract(
        'UserEscrow', linker_contract.address, token.address)
    # Transfer ownership
    tx = user_escrow_contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    user_escrow_library_v1 = testerchain.interface.w3.eth.contract(
        abi=library_v1.abi,
        address=user_escrow_contract.address,
        ContractFactoryClass=Contract)
    user_escrow_library_v2 = testerchain.interface.w3.eth.contract(
        abi=library_v2.abi,
        address=user_escrow_contract.address,
        ContractFactoryClass=Contract)

    # Check existed methods
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_library_v1.functions.firstMethod().transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = user_escrow_library_v1.functions.firstMethod().transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 20 == user_escrow_library_v1.functions.secondMethod().call({'from': user})

    # Check nonexistent methods
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_library_v2.functions.thirdMethod().transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # Can't send ETH to this version of the library
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.interface.w3.eth.sendTransaction(
            {'from': user, 'to': user_escrow_contract.address, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Update proxy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(library_v2.address).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    assert library_v1.address == linker_contract.functions.target().call()
    tx = linker_contract.functions.upgrade(library_v2.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert library_v2.address == linker_contract.functions.target().call()

    # Methods with old signatures are not worked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_library_v1.functions.firstMethod().transact({'from': user})
        testerchain.wait_for_receipt(tx)
    assert 15 == user_escrow_library_v1.functions.secondMethod().call({'from': user})

    # New ABI is worked
    assert 15 == user_escrow_library_v2.functions.secondMethod().call({'from': user})
    tx = user_escrow_library_v2.functions.firstMethod(10).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_library_v2.functions.thirdMethod().transact({'from': user})
    testerchain.wait_for_receipt(tx)

    # And can send and withdraw ETH
    tx = testerchain.interface.w3.eth.sendTransaction(
        {'from': user, 'to': user_escrow_contract.address, 'value': 1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 1 == testerchain.interface.w3.eth.getBalance(user_escrow_contract.address)
    # Only user can send ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.interface.w3.eth.sendTransaction(
            {'from': testerchain.interface.w3.eth.coinbase,
             'to': user_escrow_contract.address,
             'value': 1,
             'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert 1 == testerchain.interface.w3.eth.getBalance(user_escrow_contract.address)

    rewards = user_escrow_contract.events.ETHWithdrawn.createFilter(fromBlock='latest')
    user_balance = testerchain.interface.w3.eth.getBalance(user)
    tx = user_escrow_contract.functions.withdrawETH().transact({'from': user, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert user_balance + 1 == testerchain.interface.w3.eth.getBalance(user)
    assert 0 == testerchain.interface.w3.eth.getBalance(user_escrow_contract.address)

    events = rewards.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1 == event_args['value']
