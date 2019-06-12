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
from web3.contract import Contract

from nucypher.blockchain.eth.chains import Blockchain

RE_STAKE_FIELD = 3
LOCK_RE_STAKE_UNTIL_PERIOD_FIELD = 4

secret = (123456).to_bytes(32, byteorder='big')
secret2 = (654321).to_bytes(32, byteorder='big')


@pytest.mark.slow
def test_upgrading(testerchain, token):
    creator = testerchain.interface.w3.eth.accounts[0]
    staker = testerchain.interface.w3.eth.accounts[1]

    secret_hash = testerchain.interface.w3.keccak(secret)
    secret2_hash = testerchain.interface.w3.keccak(secret2)

    # Deploy contract
    contract_library_v1, _ = testerchain.interface.deploy_contract(
        contract_name='StakingEscrow',
        _token=token.address,
        _hoursPerPeriod=1,
        _miningCoefficient=8*10**7,
        _lockedPeriodsCoefficient=4,
        _rewardedPeriods=4,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=100,
        _maxAllowableLockedTokens=1500,
        _minWorkerPeriods=1
    )
    dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract_library_v1.address, secret_hash)

    # Deploy second version of the contract
    contract_library_v2, _ = testerchain.interface.deploy_contract(
        contract_name='StakingEscrowV2Mock',
        _token=token.address,
        _hoursPerPeriod=2,
        _miningCoefficient=2,
        _lockedPeriodsCoefficient=2,
        _rewardedPeriods=2,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=2,
        _maxAllowableLockedTokens=2,
        _minWorkerPeriods=2,
        _valueToCheck=2
    )

    contract = testerchain.interface.w3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert 1500 == contract.functions.maxAllowableLockedTokens().call()

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Initialize contract and staker
    policy_manager, _ = testerchain.interface.deploy_contract(
        'PolicyManagerForStakingEscrowMock', token.address, contract.address
    )
    tx = contract.functions.setPolicyManager(policy_manager.address).transact()
    testerchain.wait_for_receipt(tx)

    tx = contract.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(staker, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    balance = token.functions.balanceOf(staker).call()
    tx = token.functions.approve(contract.address, balance).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.deposit(balance, 1000).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setReStake(True).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.lockReStake(contract.functions.getCurrentPeriod().call() + 1).transact({'from': staker})
    testerchain.wait_for_receipt(tx)

    # Upgrade to the second version
    tx = dispatcher.functions.upgrade(contract_library_v2.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check constructor and storage values
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert 1500 == contract.functions.maxAllowableLockedTokens().call()
    assert policy_manager.address == contract.functions.policyManager().call()
    assert 2 == contract.functions.valueToCheck().call()
    # Check new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = testerchain.interface.deploy_contract(
        contract_name='StakingEscrowBad',
        _token=token.address,
        _hoursPerPeriod=2,
        _miningCoefficient=2,
        _lockedPeriodsCoefficient=2,
        _rewardedPeriods=2,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=2,
        _maxAllowableLockedTokens=2,
        _minWorkerPeriods=2
    )
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address, secret2, secret_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret2, secret_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback(secret2, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert policy_manager.address == contract.functions.policyManager().call()
    # After rollback new ABI is unavailable
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret, secret2_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    events = dispatcher.events.StateVerified.createFilter(fromBlock=0).get_all_entries()
    assert 4 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['testTarget']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[2]['args']
    event_args = events[3]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0).get_all_entries()
    assert 3 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[2]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']


@pytest.mark.slow
def test_re_stake(testerchain, token, escrow_contract):
    escrow = escrow_contract(10000)
    creator = testerchain.interface.w3.eth.accounts[0]
    ursula = testerchain.interface.w3.eth.accounts[1]
    ursula2 = testerchain.interface.w3.eth.accounts[2]

    re_stake_log = escrow.events.ReStakeSet.createFilter(fromBlock='latest')
    re_stake_lock_log = escrow.events.ReStakeLocked.createFilter(fromBlock='latest')

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Set re-stake parameter even before initialization
    assert not escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(False).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(False).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]

    events = re_stake_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula == event_args['staker']
    assert event_args['reStake']
    event_args = events[1]['args']
    assert ursula == event_args['staker']
    assert not event_args['reStake']

    # Lock re-stake parameter during 1 period
    period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.lockReStake(period + 1).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Can't set re-stake parameter in the current period
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setReStake(True).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)

    events = re_stake_lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula == event_args['staker']
    assert period + 1 == event_args['lockUntilPeriod']

    # Ursula deposits some tokens and confirms activity
    tx = token.functions.transfer(ursula, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    sub_stake = 1000
    tx = escrow.functions.deposit(sub_stake, 10).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert sub_stake == escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()
    assert 0 == escrow.functions.lockedPerPeriod(period + 1).call()

    # Confirm activity and try to mine without re-stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert sub_stake == escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Reward is not locked and stake is not changed
    assert sub_stake < escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()

    # Prepare account, withdraw reward
    balance = escrow.functions.getAllTokens(ursula).call()
    tx = escrow.functions.withdraw(balance - sub_stake).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert sub_stake == escrow.functions.getAllTokens(ursula).call()

    # Set re-stake and lock parameter
    tx = escrow.functions.setReStake(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.lockReStake(period + 6).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Can't set re-stake parameter during 6 periods
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setReStake(False).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)

    events = re_stake_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula == event_args['staker']
    assert event_args['reStake']
    events = re_stake_lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula == event_args['staker']
    assert period + 6 == event_args['lockUntilPeriod']

    # Confirm activity and try to mine with re-stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert sub_stake == escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Entire reward is locked
    balance = escrow.functions.getAllTokens(ursula).call()
    new_sub_stake = escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake < balance
    assert balance == new_sub_stake
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert new_sub_stake == escrow.functions.lockedPerPeriod(period).call()

    # Mine with re-stake again
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    sub_stake = new_sub_stake
    assert sub_stake == escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Entire reward is locked
    balance = escrow.functions.getAllTokens(ursula).call()
    new_sub_stake = escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake < balance
    assert balance == new_sub_stake
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()

    # Prepares test case:
    # two Ursula with the same sum of sub stakes and duration with two confirmed period in a past
    sub_stake_1 = new_sub_stake
    sub_stake_2 = sub_stake_1 // 2
    stake = sub_stake_1 + sub_stake_2
    sub_stake_duration = escrow.functions.getSubStakeInfo(ursula, 0).call()[2]
    tx = escrow.functions.deposit(sub_stake_2, sub_stake_duration).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(ursula2, stake).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, stake).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(stake, sub_stake_duration).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    # Checks preparation
    period = escrow.functions.getCurrentPeriod().call()
    assert stake == escrow.functions.getAllTokens(ursula).call()
    assert stake == escrow.functions.getAllTokens(ursula2).call()
    assert stake == escrow.functions.getLockedTokens(ursula).call()
    assert stake == escrow.functions.getLockedTokens(ursula2).call()
    assert sub_stake_1 == escrow.functions.getSubStakeInfo(ursula, 0).call()[3]
    assert sub_stake_2 == escrow.functions.getSubStakeInfo(ursula, 1).call()[3]
    assert 2 * stake == escrow.functions.lockedPerPeriod(period - 2).call()
    assert 2 * stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()

    # Compare mining with re-stake and without for two surpassed periods
    # The first is Ursula2 because of Ursula1's re-stake will change sub stake ratio for `period - 1`
    # (stake/lockedPerPeriod) and it will affect next mining
    tx = escrow.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    ursula_reward = escrow.functions.getAllTokens(ursula).call() - stake
    ursula2_reward = escrow.functions.getAllTokens(ursula2).call() - stake
    assert 0 < ursula2_reward
    assert ursula_reward > ursula2_reward
    # Ursula2's stake has not changed
    assert stake == escrow.functions.getLockedTokens(ursula2).call()

    # To calculate amount of re-stake we can split Ursula1's reward according sub stakes ratio:
    # first sub stake is 2/3 of entire stake and second sub stake is 1/3
    re_stake_for_first_sub_stake = ursula_reward * 2 // 3
    re_stake_for_second_sub_stake = ursula_reward - re_stake_for_first_sub_stake
    # Check re-stake for Ursula1's sub stakes
    assert stake + ursula_reward == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake_1 + re_stake_for_first_sub_stake == escrow.functions.getSubStakeInfo(ursula, 0).call()[3]
    assert sub_stake_2 + re_stake_for_second_sub_stake == escrow.functions.getSubStakeInfo(ursula, 1).call()[3]

    # Ursula2's reward for both confirmed periods will be equal because of equal stakes for this periods
    # Also this reward will be equal to Ursula1's reward for the first period
    # Because re-stake affects only the second confirmed period
    reward_for_first_period = ursula2_reward // 2
    # Check re-stake for global `lockedPerPeriod` values
    assert 2 * stake == escrow.functions.lockedPerPeriod(period - 2).call()
    assert 2 * stake + reward_for_first_period == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()

    # Can't turn off re-stake parameter during one more period
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setReStake(False).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)

    # Confirm activity and try to mine without re-stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)

    # Now turn off re-stake
    tx = escrow.functions.setReStake(False).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(ursula).call()[RE_STAKE_FIELD]

    events = re_stake_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula == event_args['staker']
    assert not event_args['reStake']

    # Check before mining
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    sub_stake = escrow.functions.getLockedTokensInPast(ursula, 1).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)

    # Reward is not locked and stake is not changed
    assert sub_stake < escrow.functions.getAllTokens(ursula).call()
    assert sub_stake == escrow.functions.getLockedTokensInPast(ursula, 1).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()


@pytest.mark.slow
def test_worker(testerchain, token, escrow_contract):
    escrow = escrow_contract(10000)
    creator, ursula1, ursula2, ursula3, worker1, worker2, worker3, *everyone_else = \
        testerchain.interface.w3.eth.accounts

    worker_log = escrow.events.WorkerSet.createFilter(fromBlock='latest')

    # Initialize escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Deploy intermediary contracts
    intermediary1, _ = testerchain.interface.deploy_contract('Intermediary', token.address, escrow.address)
    intermediary2, _ = testerchain.interface.deploy_contract('Intermediary', token.address, escrow.address)
    intermediary3, _ = testerchain.interface.deploy_contract('Intermediary', token.address, escrow.address)

    # Prepare stakers: two with intermediary contract and one just a staker
    sub_stake = 1000
    duration = 100
    tx = token.functions.transfer(intermediary1.address, sub_stake).transact()
    testerchain.wait_for_receipt(tx)
    tx = intermediary1.functions.deposit(sub_stake, duration).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert sub_stake == escrow.functions.getAllTokens(intermediary1.address).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getWorkerFromStaker(intermediary1.address).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getStakerFromWorker(intermediary1.address).call()

    tx = token.functions.transfer(intermediary2.address, sub_stake).transact()
    testerchain.wait_for_receipt(tx)
    tx = intermediary2.functions.deposit(sub_stake, duration).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert sub_stake == escrow.functions.getAllTokens(intermediary2.address).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getWorkerFromStaker(intermediary2.address).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getStakerFromWorker(intermediary2.address).call()

    tx = token.functions.transfer(ursula3, sub_stake).transact()
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approveAndCall(escrow.address, sub_stake, testerchain.interface.w3.toBytes(duration)) \
        .transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert sub_stake == escrow.functions.getAllTokens(ursula3).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getWorkerFromStaker(ursula3).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getStakerFromWorker(ursula3).call()

    # Ursula can't confirm activity because there is no worker by default
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula can't use another staker as worker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.setWorker(ursula3).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula set worker and now worker can confirm activity
    tx = intermediary1.functions.setWorker(worker1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert worker1 == escrow.functions.getWorkerFromStaker(intermediary1.address).call()
    assert intermediary1.address == escrow.functions.getStakerFromWorker(worker1).call()
    tx = escrow.functions.confirmActivity().transact({'from': worker1})
    testerchain.wait_for_receipt(tx)

    number_of_events = 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert intermediary1.address == event_args['staker']
    assert worker1 == event_args['worker']
    worker1_start_period = escrow.functions.getCurrentPeriod().call()
    assert worker1_start_period == event_args['startPeriod']

    # Only worker can confirm activity
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.setWorker(ursula3).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    # Worker is in use so other stakers can't set him
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary2.functions.setWorker(worker1).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)

    # Worker can't be a staker
    tx = token.functions.approve(escrow.address, sub_stake).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([worker1], [sub_stake], [duration]).transact()
        testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(worker1, sub_stake).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, sub_stake, testerchain.interface.w3.toBytes(duration)) \
            .transact({'from': worker1})
        testerchain.wait_for_receipt(tx)

    # Can't change worker twice in the same period
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.setWorker(worker2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # But she can unset her worker
    tx = intermediary1.functions.setWorker(Blockchain.NULL_ADDRESS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert Blockchain.NULL_ADDRESS == escrow.functions.getWorkerFromStaker(intermediary1.address).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert intermediary1.address == event_args['staker']
    # Even though the worker has been unset...
    assert Blockchain.NULL_ADDRESS == event_args['worker']
    # ... the previous start period remains.
    assert worker1_start_period == event_args['startPeriod']

    # The staker can't set a new worker until the previous worker's time has passed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.setWorker(worker2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Let's advance one period and change the worker
    testerchain.time_travel(hours=1)
    tx = intermediary1.functions.setWorker(worker2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert worker2 == escrow.functions.getWorkerFromStaker(intermediary1.address).call()
    assert intermediary1.address == escrow.functions.getStakerFromWorker(worker2).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getStakerFromWorker(worker1).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert intermediary1.address == event_args['staker']
    assert worker2 == event_args['worker']
    assert escrow.functions.getCurrentPeriod().call() == event_args['startPeriod']

    # Now the previous worker can no longer confirm
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': worker1})
        testerchain.wait_for_receipt(tx)
    # Only new worker can
    tx = escrow.functions.confirmActivity().transact({'from': worker2})
    testerchain.wait_for_receipt(tx)

    # Another staker can use a free worker
    tx = intermediary2.functions.setWorker(worker1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert worker1 == escrow.functions.getWorkerFromStaker(intermediary2.address).call()
    assert intermediary2.address == escrow.functions.getStakerFromWorker(worker1).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert intermediary2.address == event_args['staker']
    assert worker1 == event_args['worker']
    assert escrow.functions.getCurrentPeriod().call() == event_args['startPeriod']

    # The first worker still can't be a staker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, sub_stake, testerchain.interface.w3.toBytes(duration)) \
            .transact({'from': worker1})
        testerchain.wait_for_receipt(tx)

    # Change worker again
    testerchain.time_travel(hours=1)
    tx = intermediary2.functions.setWorker(ursula2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert ursula2 == escrow.functions.getWorkerFromStaker(intermediary2.address).call()
    assert intermediary2.address == escrow.functions.getStakerFromWorker(ursula2).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getStakerFromWorker(worker1).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert intermediary2.address == event_args['staker']
    assert ursula2 == event_args['worker']
    assert escrow.functions.getCurrentPeriod().call() == event_args['startPeriod']

    # The first worker is free and can deposit tokens and become a staker
    tx = escrow.functions.preDeposit([worker1], [sub_stake], [duration]).transact()
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approveAndCall(escrow.address, sub_stake, testerchain.interface.w3.toBytes(duration)) \
        .transact({'from': worker1})
    testerchain.wait_for_receipt(tx)
    assert 2 * sub_stake == escrow.functions.getAllTokens(worker1).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getStakerFromWorker(worker1).call()
    assert Blockchain.NULL_ADDRESS == escrow.functions.getWorkerFromStaker(worker1).call()

    # Ursula can't use the first worker again because worker is a staker now
    testerchain.time_travel(hours=1)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.setWorker(worker1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula without intermediary contract can set itself as worker
    # (Probably not her best idea, but whatever)
    tx = escrow.functions.setWorker(ursula3).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert ursula3 == escrow.functions.getStakerFromWorker(ursula3).call()
    assert ursula3 == escrow.functions.getWorkerFromStaker(ursula3).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert ursula3 == event_args['staker']
    assert ursula3 == event_args['worker']
    assert escrow.functions.getCurrentPeriod().call() == event_args['startPeriod']

    # Now Ursula can confirm activity
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Ursula set worker again
    testerchain.time_travel(hours=1)
    tx = escrow.functions.setWorker(worker3).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert ursula3 == escrow.functions.getStakerFromWorker(worker3).call()
    assert worker3 == escrow.functions.getWorkerFromStaker(ursula3).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert ursula3 == event_args['staker']
    assert worker3 == event_args['worker']
    assert escrow.functions.getCurrentPeriod().call() == event_args['startPeriod']

    tx = escrow.functions.confirmActivity().transact({'from': worker3})
    testerchain.wait_for_receipt(tx)

    # Ursula try to set contract as worker
    testerchain.time_travel(hours=1)
    tx = escrow.functions.setWorker(intermediary3.address).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert number_of_events == len(events)
    event_args = events[-1]['args']
    assert ursula3 == event_args['staker']
    assert intermediary3.address == event_args['worker']
    assert escrow.functions.getCurrentPeriod().call() == event_args['startPeriod']

    # But can't confirm activity using an intermediary contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary3.functions.confirmActivity().transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)
