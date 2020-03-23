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


import os
import pytest
from eth_utils import keccak
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract

from nucypher.blockchain.eth.interfaces import BlockchainInterface


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
    tx = token.functions.transfer(preallocation_escrow.address, 300).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 1300 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    withdraws = preallocation_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')

    # Only owner can withdraw available tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(1).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.withdrawTokens(300).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 300 == token.functions.balanceOf(owner).call()
    assert 1000 == token.functions.balanceOf(preallocation_escrow.address).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['owner']
    assert 300 == event_args['value']

    # Wait some time
    testerchain.time_travel(seconds=500)
    # Tokens are still locked
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    assert 300 == token.functions.balanceOf(owner).call()

    # Wait more time and withdraw all after unlocking
    testerchain.time_travel(seconds=500)
    assert 0 == preallocation_escrow.functions.getLockedTokens().call()
    tx = preallocation_escrow.functions.withdrawTokens(1000).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 0 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 1300 == token.functions.balanceOf(owner).call()

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
    tx = token.functions.approveAndCall(preallocation_escrow.address, 2000, testerchain.w3.toBytes(1000))\
        .transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 2000 == preallocation_escrow.functions.getLockedTokens().call()

    events = deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator == event_args['sender']
    assert 2000 == event_args['value']
    assert 1000 == event_args['duration']

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
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.setWindDown(True).transact({'from': owner})
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
    wind_down_logs = preallocation_escrow_interface.events.WindDownSet.createFilter(fromBlock='latest')

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

    # Test wind-down
    tx = preallocation_escrow_interface.functions.setWindDown(True).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.windDown().call()

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

    events = wind_down_logs.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert event_args['windDown']

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
        tx = preallocation_escrow_interface.functions.withdrawPolicyReward().transact({'from': owner, 'gas_price': 0})
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
        tx = preallocation_escrow_interface.functions.withdrawPolicyReward().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawETH().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Owner withdraws reward
    tx = preallocation_escrow_interface.functions.withdrawPolicyReward().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 10000 == testerchain.client.get_balance(preallocation_escrow.address)
    assert owner_balance == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(policy_manager.address)
    assert 10000 == testerchain.client.get_balance(preallocation_escrow.address)

    events = staker_reward.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 10000 == event_args['value']

    events = rewards.get_all_entries()
    assert 0 == len(events)

    tx = preallocation_escrow.functions.withdrawETH().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == testerchain.client.get_balance(preallocation_escrow.address)
    assert owner_balance + 10000 == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(policy_manager.address)
    assert 0 == testerchain.client.get_balance(preallocation_escrow.address)

    events = rewards.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['owner']
    assert 10000 == event_args['value']

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


@pytest.mark.slow
def test_reentrancy(testerchain, preallocation_escrow, deploy_contract):
    owner = testerchain.client.accounts[1]

    # Prepare contracts
    reentrancy_contract, _ = deploy_contract('ReentrancyTest')
    contract_address = reentrancy_contract.address
    tx = preallocation_escrow.functions.transferOwnership(contract_address).transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # Transfer ETH to user escrow
    value = 10000
    tx = reentrancy_contract.functions.setData(1, preallocation_escrow.address, value, bytes()).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': contract_address, 'value': value})
    testerchain.wait_for_receipt(tx)
    assert testerchain.client.get_balance(preallocation_escrow.address) == value

    # Try to withdraw ETH twice
    balance = testerchain.w3.eth.getBalance(contract_address)
    transaction = preallocation_escrow.functions.withdrawETH().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance


@pytest.mark.slow
def test_worklock(testerchain, worklock, preallocation_escrow, preallocation_escrow_interface, staking_interface):
    """
    Test worklock functions in the preallocation escrow
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    bids = preallocation_escrow_interface.events.Bid.createFilter(fromBlock='latest')
    claims = preallocation_escrow_interface.events.Claimed.createFilter(fromBlock='latest')
    refunds = preallocation_escrow_interface.events.Refund.createFilter(fromBlock='latest')
    cancellations = preallocation_escrow_interface.events.BidCanceled.createFilter(fromBlock='latest')
    compensations = preallocation_escrow_interface.events.CompensationWithdrawn.createFilter(fromBlock='latest')

    # Owner can't use the staking interface directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.bid(0).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.cancelBid().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.withdrawCompensation().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.claim().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.refund().transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Send ETH to to the escrow
    bid = 10000
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': preallocation_escrow.address, 'value': 2 * bid})
    testerchain.wait_for_receipt(tx)

    # Bid
    assert worklock.functions.depositedETH().call() == 0
    assert testerchain.client.get_balance(preallocation_escrow.address) == 2 * bid
    tx = preallocation_escrow_interface.functions.bid(bid).transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.depositedETH().call() == bid
    assert testerchain.client.get_balance(preallocation_escrow.address) == bid

    events = bids.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['depositedETH'] == bid

    # Cancel bid
    tx = preallocation_escrow_interface.functions.cancelBid().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.depositedETH().call() == 0
    assert testerchain.client.get_balance(preallocation_escrow.address) == 2 * bid

    events = cancellations.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner

    # Withdraw compensation
    compensation = 11000
    tx = worklock.functions.sendCompensation().transact({'from': creator, 'value': compensation, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.compensation().call() == compensation
    tx = preallocation_escrow_interface.functions.withdrawCompensation().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.compensation().call() == 0
    assert testerchain.client.get_balance(preallocation_escrow.address) == 2 * bid + compensation

    events = compensations.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner

    # Claim
    assert worklock.functions.claimed().call() == 0
    tx = preallocation_escrow_interface.functions.claim().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.claimed().call() == 1

    events = claims.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['claimedTokens'] == 1

    # Withdraw refund
    refund = 12000
    tx = worklock.functions.sendRefund().transact({'from': creator, 'value': refund, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.refundETH().call() == refund
    tx = preallocation_escrow_interface.functions.refund().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.refundETH().call() == 0
    assert testerchain.client.get_balance(preallocation_escrow.address) == 2 * bid + compensation + refund

    events = refunds.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['refundETH'] == refund


@pytest.mark.slow
def test_interface_without_worklock(testerchain, deploy_contract, token, escrow, policy_manager, worklock):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    staking_interface, _ = deploy_contract(
        'StakingInterface', token.address, escrow.address, policy_manager.address, worklock.address)
    secret = os.urandom(32)
    secret_hash = keccak(secret)
    router, _ = deploy_contract('StakingInterfaceRouter', staking_interface.address, secret_hash)

    preallocation_escrow, _ = deploy_contract('PreallocationEscrow', router.address, token.address, escrow.address)
    # Transfer ownership
    tx = preallocation_escrow.functions.transferOwnership(owner).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    preallocation_escrow_interface = testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=preallocation_escrow.address,
        ContractFactoryClass=Contract)

    # All worklock methods work
    tx = preallocation_escrow_interface.functions.bid(0).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface.functions.cancelBid().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface.functions.withdrawCompensation().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface.functions.claim().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface.functions.refund().transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # Test interface without worklock
    secret2 = os.urandom(32)
    secret2_hash = keccak(secret2)
    staking_interface, _ = deploy_contract(
        'StakingInterface', token.address, escrow.address, policy_manager.address, BlockchainInterface.NULL_ADDRESS)
    tx = router.functions.upgrade(staking_interface.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Current version of interface doesn't have worklock contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.bid(0).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.cancelBid().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.withdrawCompensation().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.claim().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.refund().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
