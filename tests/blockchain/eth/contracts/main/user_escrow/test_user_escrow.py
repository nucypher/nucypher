"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import pytest
from eth_tester.exceptions import TransactionFailed


@pytest.mark.slow
def test_escrow(testerchain, token, user_escrow):
    creator = testerchain.w3.eth.accounts[0]
    user = testerchain.w3.eth.accounts[1]
    deposits = user_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the user escrow and lock them
    tx = token.functions.approve(user_escrow.address, 2000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check locked tokens
    assert 1000 == token.functions.balanceOf(user_escrow.address).call()
    assert user == user_escrow.functions.owner().call()
    assert 1000 == user_escrow.functions.getLockedTokens().call()

    events = deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator == event_args['sender']
    assert 1000 == event_args['value']
    assert 1000 == event_args['duration']

    # Can't deposit tokens again, only once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # Transfer more tokens without locking
    tx = token.functions.transfer(user_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()
    assert 1000 == user_escrow.functions.getLockedTokens().call()

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
    # Tokens are still locked
    assert 1000 == user_escrow.functions.getLockedTokens().call()

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(user).call()

    # Wait more time and withdraw all after unlocking
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
def test_staker(testerchain, token, escrow, user_escrow, user_escrow_proxy, proxy):
    """
    Test staker functions in the user escrow
    """
    creator = testerchain.w3.eth.accounts[0]
    user = testerchain.w3.eth.accounts[1]

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

    # Only user can deposit tokens to the staker escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.depositAsStaker(1000, 5).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.depositAsStaker(10000, 5).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    staker_deposits = user_escrow_proxy.events.DepositedAsStaker.createFilter(fromBlock='latest')

    # Deposit some tokens to the staking escrow
    tx = user_escrow_proxy.functions.depositAsStaker(1500, 5).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert user_escrow.address == escrow.functions.node().call()
    assert 1500 == escrow.functions.value().call()
    assert 1500 == escrow.functions.lockedValue().call()
    assert 5 == escrow.functions.periods().call()
    assert 11500 == token.functions.balanceOf(escrow.address).call()
    assert 500 == token.functions.balanceOf(user_escrow.address).call()

    events = staker_deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert 1500 == event_args['value']
    assert 5 == event_args['periods']

    # Can't withdraw because tokens are locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawTokens(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # User can't use the proxy contract directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.lock(100, 1).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.divideStake(1, 100, 1).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.mint().transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.withdrawAsStaker(100).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.setReStake(True).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.lockReStake(0).transact({'from': user})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = proxy.functions.setWorker(user).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    locks = user_escrow_proxy.events.Locked.createFilter(fromBlock='latest')
    divides = user_escrow_proxy.events.Divided.createFilter(fromBlock='latest')
    mints = user_escrow_proxy.events.Mined.createFilter(fromBlock='latest')
    staker_withdraws = user_escrow_proxy.events.WithdrawnAsStaker.createFilter(fromBlock='latest')
    withdraws = user_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')
    re_stakes = user_escrow_proxy.events.ReStakeSet.createFilter(fromBlock='latest')
    re_stake_locks = user_escrow_proxy.events.ReStakeLocked.createFilter(fromBlock='latest')
    worker_logs = user_escrow_proxy.events.WorkerSet.createFilter(fromBlock='latest')

    # Use stakers methods through the user escrow
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
    tx = user_escrow_proxy.functions.mint().transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 2500 == escrow.functions.value().call()
    tx = user_escrow_proxy.functions.withdrawAsStaker(1500).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.value().call()
    assert 10000 == token.functions.balanceOf(escrow.address).call()
    assert 2000 == token.functions.balanceOf(user_escrow.address).call()
    tx = user_escrow_proxy.functions.withdrawAsStaker(1000).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 0 == escrow.functions.value().call()
    assert 9000 == token.functions.balanceOf(escrow.address).call()
    assert 3000 == token.functions.balanceOf(user_escrow.address).call()

    # Test re-stake methods
    tx = user_escrow_proxy.functions.setReStake(True).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.reStake().call()
    tx = user_escrow_proxy.functions.lockReStake(123).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 123 == escrow.functions.lockReStakeUntilPeriod().call()

    # Test setting worker
    tx = user_escrow_proxy.functions.setWorker(user).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert user == escrow.functions.worker().call()

    events = locks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert 100 == event_args['value']
    assert 1 == event_args['periods']

    events = divides.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert 1 == event_args['index']
    assert 100 == event_args['newValue']
    assert 1 == event_args['periods']

    events = mints.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']

    events = staker_withdraws.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert 1500 == event_args['value']
    event_args = events[1]['args']
    assert user == event_args['sender']
    assert 1000 == event_args['value']

    events = re_stakes.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert event_args['reStake']

    events = re_stake_locks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert 123 == event_args['lockUntilPeriod']

    events = worker_logs.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert user == event_args['worker']

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
    """
    Test policy manager functions in the user escrow
    """
    creator = testerchain.w3.eth.accounts[0]
    user = testerchain.w3.eth.accounts[1]
    user_balance = testerchain.w3.eth.getBalance(user)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.withdrawPolicyReward().transact({'from': user, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawETH().transact({'from': user, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert user_balance == testerchain.w3.eth.getBalance(user)
    assert 0 == testerchain.w3.eth.getBalance(user_escrow.address)

    # Send ETH to the policy manager as a reward for the user
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.w3.eth.coinbase, 'to': policy_manager.address, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    staker_reward = user_escrow_proxy.events.PolicyRewardWithdrawn.createFilter(fromBlock='latest')
    rewards = user_escrow.events.ETHWithdrawn.createFilter(fromBlock='latest')

    # Only user can withdraw reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy.functions.withdrawPolicyReward().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow.functions.withdrawETH().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # User withdraws reward
    tx = user_escrow_proxy.functions.withdrawPolicyReward().transact({'from': user, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert user_balance + 10000 == testerchain.w3.eth.getBalance(user)
    assert 0 == testerchain.w3.eth.getBalance(policy_manager.address)
    assert 0 == testerchain.w3.eth.getBalance(user_escrow.address)

    events = staker_reward.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['sender']
    assert 10000 == event_args['value']

    events = rewards.get_all_entries()
    assert 0 == len(events)

    # Only user can set min reward rate
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
    assert user == event_args['sender']
    assert 222 == event_args['value']
