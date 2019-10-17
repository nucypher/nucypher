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
def test_escrow(testerchain, token, preallocation_escrow):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    deposits = preallocation_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the preallocation escrow and lock them
    tx = token.functions.approve(preallocation_escrow.address, 2000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check locked tokens
    assert 1000 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert owner == preallocation_escrow.functions.owner().call()
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    events = deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator == event_args['sender']
    assert 1000 == event_args['value']
    assert 1000 == event_args['duration']

    # Can't deposit tokens again, only once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Transfer more tokens without locking
    tx = token.functions.transfer(preallocation_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    withdraws = preallocation_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')

    # Only owner can withdraw available tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.withdrawTokens(1000).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(owner).call()
    assert 1000 == token.functions.balanceOf(preallocation_escrow.address).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['owner']
    assert 1000 == event_args['value']

    # Wait some time
    testerchain.time_travel(seconds=500)
    # Tokens are still locked
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(owner).call()

    # Wait more time and withdraw all after unlocking
    testerchain.time_travel(seconds=500)
    assert 0 == preallocation_escrow.functions.getLockedTokens().call()
    tx = preallocation_escrow.functions.withdrawTokens(1000).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 0 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 2000 == token.functions.balanceOf(owner).call()

    events = withdraws.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert owner == event_args['owner']
    assert 1000 == event_args['value']


@pytest.mark.slow
def test_staker(testerchain, token, escrow, preallocation_escrow, preallocation_escrow_interface, staking_interface):
    """
    Test staker functions in the preallocation escrow
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    deposits = preallocation_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the preallocation escrow and lock them
    tx = token.functions.approve(preallocation_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(preallocation_escrow.address, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(preallocation_escrow.address).call()

    events = deposits.get_all_entries()
    assert 1 == len(events)

    # Only owner can deposit tokens to the staker escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.depositAsStaker(1000, 5).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    # Can't deposit more than amount in the preallocation escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.depositAsStaker(10000, 5).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    staker_deposits = preallocation_escrow_interface.events.DepositedAsStaker.createFilter(fromBlock='latest')

    # Deposit some tokens to the staking escrow
    tx = preallocation_escrow_interface.functions.depositAsStaker(1500, 5).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert preallocation_escrow.address == escrow.functions.node().call()
    assert 1500 == escrow.functions.value().call()
    assert 1500 == escrow.functions.lockedValue().call()
    assert 5 == escrow.functions.periods().call()
    assert 11500 == token.functions.balanceOf(escrow.address).call()
    assert 500 == token.functions.balanceOf(preallocation_escrow.address).call()

    events = staker_deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 1500 == event_args['value']
    assert 5 == event_args['periods']

    # Can't withdraw because tokens are locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Owner can't use the staking interface directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.lock(100, 1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.divideStake(1, 100, 1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.mint().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.withdrawAsStaker(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.setReStake(True).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.lockReStake(0).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.setWorker(owner).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.prolongStake(2, 2).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    locks = preallocation_escrow_interface.events.Locked.createFilter(fromBlock='latest')
    divides = preallocation_escrow_interface.events.Divided.createFilter(fromBlock='latest')
    mints = preallocation_escrow_interface.events.Mined.createFilter(fromBlock='latest')
    staker_withdraws = preallocation_escrow_interface.events.WithdrawnAsStaker.createFilter(fromBlock='latest')
    withdraws = preallocation_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')
    re_stakes = preallocation_escrow_interface.events.ReStakeSet.createFilter(fromBlock='latest')
    re_stake_locks = preallocation_escrow_interface.events.ReStakeLocked.createFilter(fromBlock='latest')
    worker_logs = preallocation_escrow_interface.events.WorkerSet.createFilter(fromBlock='latest')
    prolong_logs = preallocation_escrow_interface.events.Prolonged.createFilter(fromBlock='latest')

    # Use stakers methods through the preallocation escrow
    tx = preallocation_escrow_interface.functions.lock(100, 1).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 1500 == escrow.functions.value().call()
    assert 1600 == escrow.functions.lockedValue().call()
    assert 6 == escrow.functions.periods().call()
    tx = preallocation_escrow_interface.functions.divideStake(1, 100, 1).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 1500 == escrow.functions.value().call()
    assert 1700 == escrow.functions.lockedValue().call()
    assert 1 == escrow.functions.index().call()
    assert 7 == escrow.functions.periods().call()
    tx = preallocation_escrow_interface.functions.mint().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 2500 == escrow.functions.value().call()
    tx = preallocation_escrow_interface.functions.withdrawAsStaker(1500).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.value().call()
    assert 10000 == token.functions.balanceOf(escrow.address).call()
    assert 2000 == token.functions.balanceOf(preallocation_escrow.address).call()
    tx = preallocation_escrow_interface.functions.withdrawAsStaker(1000).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 0 == escrow.functions.value().call()
    assert 9000 == token.functions.balanceOf(escrow.address).call()
    assert 3000 == token.functions.balanceOf(preallocation_escrow.address).call()
    tx = preallocation_escrow_interface.functions.prolongStake(2, 2).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 2 == escrow.functions.index().call()
    assert 9 == escrow.functions.periods().call()

    # Test re-stake methods
    tx = preallocation_escrow_interface.functions.setReStake(True).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.reStake().call()
    tx = preallocation_escrow_interface.functions.lockReStake(123).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 123 == escrow.functions.lockReStakeUntilPeriod().call()

    # Test setting worker
    tx = preallocation_escrow_interface.functions.setWorker(owner).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert owner == escrow.functions.worker().call()

    events = locks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 100 == event_args['value']
    assert 1 == event_args['periods']

    events = divides.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 1 == event_args['index']
    assert 100 == event_args['newValue']
    assert 1 == event_args['periods']

    events = mints.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']

    events = staker_withdraws.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 1500 == event_args['value']
    event_args = events[1]['args']
    assert owner == event_args['sender']
    assert 1000 == event_args['value']

    events = re_stakes.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert event_args['reStake']

    events = re_stake_locks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 123 == event_args['lockUntilPeriod']

    events = worker_logs.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert owner == event_args['worker']

    events = prolong_logs.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 2 == event_args['index']
    assert 2 == event_args['periods']

    # Owner can withdraw reward for mining but no more than locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(2500).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.withdrawTokens(1000).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 1000 == token.functions.balanceOf(owner).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['owner']
    assert 1000 == event_args['value']


@pytest.mark.slow
def test_policy(testerchain, policy_manager, preallocation_escrow, preallocation_escrow_interface):
    """
    Test policy manager functions in the preallocation escrow
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    owner_balance = testerchain.client.get_balance(owner)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.withdrawPolicyReward(owner).transact({'from': owner, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawETH().transact({'from': owner, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert owner_balance == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(preallocation_escrow.address)

    # Send ETH to the policy manager as a reward for the owner
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': policy_manager.address, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    staker_reward = preallocation_escrow_interface.events.PolicyRewardWithdrawn.createFilter(fromBlock='latest')
    rewards = preallocation_escrow.events.ETHWithdrawn.createFilter(fromBlock='latest')

    # Only owner can withdraw reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.withdrawPolicyReward(creator).transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawETH().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Owner withdraws reward
    tx = preallocation_escrow_interface.functions.withdrawPolicyReward(owner).transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert owner_balance + 10000 == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(policy_manager.address)
    assert 0 == testerchain.client.get_balance(preallocation_escrow.address)

    events = staker_reward.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 10000 == event_args['value']

    events = rewards.get_all_entries()
    assert 0 == len(events)

    # Only owner can set min reward rate
    min_reward_sets = preallocation_escrow_interface.events.MinRewardRateSet.createFilter(fromBlock='latest')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.setMinRewardRate(333).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface.functions.setMinRewardRate(222).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 222 == policy_manager.functions.minRewardRate().call()

    events = min_reward_sets.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 222 == event_args['value']
