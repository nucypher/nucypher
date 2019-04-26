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


VALUE_FIELD = 0
RE_STAKE_FIELD = 3
LOCK_RE_STAKE_UNTIL_PERIOD_FIELD = 4

secret = (123456).to_bytes(32, byteorder='big')
secret2 = (654321).to_bytes(32, byteorder='big')


@pytest.mark.slow
def test_upgrading(testerchain, token):
    creator = testerchain.interface.w3.eth.accounts[0]
    miner = testerchain.interface.w3.eth.accounts[1]

    secret_hash = testerchain.interface.w3.keccak(secret)
    secret2_hash = testerchain.interface.w3.keccak(secret2)

    # Deploy contract
    contract_library_v1, _ = testerchain.interface.deploy_contract(
        contract_name='MinersEscrow',
        _token=token.address,
        _hoursPerPeriod=1,
        _miningCoefficient=8*10**7,
        _lockedPeriodsCoefficient=4,
        _rewardedPeriods=4,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=100,
        _maxAllowableLockedTokens=1500
    )
    dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract_library_v1.address, secret_hash)

    # Deploy second version of the contract
    contract_library_v2, _ = testerchain.interface.deploy_contract(
        contract_name='MinersEscrowV2Mock',
        _token=token.address,
        _hoursPerPeriod=2,
        _miningCoefficient=2,
        _lockedPeriodsCoefficient=2,
        _rewardedPeriods=2,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=2,
        _maxAllowableLockedTokens=2,
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

    # Initialize contract and miner
    policy_manager, _ = testerchain.interface.deploy_contract(
        'PolicyManagerForMinersEscrowMock', token.address, contract.address
    )
    tx = contract.functions.setPolicyManager(policy_manager.address).transact()
    testerchain.wait_for_receipt(tx)

    tx = contract.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(miner, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    balance = token.functions.balanceOf(miner).call()
    tx = token.functions.approve(contract.address, balance).transact({'from': miner})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.deposit(balance, 1000).transact({'from': miner})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setReStake(True).transact({'from': miner})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.lockReStake(contract.functions.getCurrentPeriod().call() + 1).transact({'from': miner})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWorker(miner).transact({'from': miner})
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
        contract_name='MinersEscrowBad',
        _token=token.address,
        _hoursPerPeriod=2,
        _miningCoefficient=2,
        _lockedPeriodsCoefficient=2,
        _rewardedPeriods=2,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=2,
        _maxAllowableLockedTokens=2
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
    assert not escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(False).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(False).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]

    events = re_stake_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula == event_args['miner']
    assert event_args['reStake']
    event_args = events[1]['args']
    assert ursula == event_args['miner']
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
    assert ursula == event_args['miner']
    assert period + 1 == event_args['lockUntilPeriod']

    # Ursula deposits some tokens and confirms activity
    tx = token.functions.transfer(ursula, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    sub_stake = 1000
    tx = escrow.functions.deposit(sub_stake, 10).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert sub_stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()
    assert 0 == escrow.functions.lockedPerPeriod(period + 1).call()

    # Confirm activity and try to mine without re-stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert sub_stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Reward is not locked and stake is not changed
    assert sub_stake < escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()

    # Prepare account, withdraw reward
    balance = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    tx = escrow.functions.withdraw(balance - sub_stake).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert sub_stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]

    # Set re-stake and lock parameter
    tx = escrow.functions.setReStake(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]
    tx = escrow.functions.lockReStake(period + 6).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Can't set re-stake parameter during 6 periods
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setReStake(False).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)

    events = re_stake_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula == event_args['miner']
    assert event_args['reStake']
    events = re_stake_lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula == event_args['miner']
    assert period + 6 == event_args['lockUntilPeriod']

    # Confirm activity and try to mine with re-stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert sub_stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Entire reward is locked
    balance = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    new_sub_stake = escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake < balance
    assert balance == new_sub_stake
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert new_sub_stake == escrow.functions.lockedPerPeriod(period).call()

    # Mine with re-stake again
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    sub_stake = new_sub_stake
    assert sub_stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    # Entire reward is locked
    balance = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
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
    assert stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert stake == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
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
    ursula_reward = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD] - stake
    ursula2_reward = escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD] - stake
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
    assert not escrow.functions.minerInfo(ursula).call()[RE_STAKE_FIELD]

    events = re_stake_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula == event_args['miner']
    assert not event_args['reStake']

    # Check before mining
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    sub_stake = escrow.functions.getLockedTokensInPast(ursula, 1).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)

    # Reward is not locked and stake is not changed
    assert sub_stake < escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert sub_stake == escrow.functions.getLockedTokensInPast(ursula, 1).call()
    assert sub_stake == escrow.functions.getLockedTokens(ursula).call()
    assert sub_stake == escrow.functions.lockedPerPeriod(period - 1).call()


@pytest.mark.slow
def test_worker(testerchain, token, escrow_contract):
    pass
