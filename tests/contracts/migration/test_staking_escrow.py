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

from nucypher.blockchain.eth.constants import NULL_ADDRESS


def test_staking_escrow_migration(testerchain, token_economics, token, deploy_contract):
    creator, staker1, staker2, staker3, staker4, staker5, staker6, staker7, staker8, *everyone_else = testerchain.client.accounts

    # Deploy PolicyManager, Adjudicator and WorkLock mocks
    policy_manager, _ = deploy_contract(
        'PolicyManagerForStakingEscrowMock', NULL_ADDRESS, token_economics.seconds_per_period
    )
    adjudicator, _ = deploy_contract('AdjudicatorForStakingEscrowMock', token_economics.reward_coefficient)
    worklock, _ = deploy_contract('WorkLockForStakingEscrowMock', token.address)

    # Deploy old contract
    deploy_args = token_economics.staking_deployment_parameters
    deploy_args = (deploy_args[0], *deploy_args[2:])
    staking_escrow_old_library, _ = deploy_contract(
        'StakingEscrowOld',
        token.address,
        *deploy_args,
        False  # testContract
    )
    dispatcher, _ = deploy_contract('Dispatcher', staking_escrow_old_library.address)

    contract = testerchain.client.get_contract(
        abi=staking_escrow_old_library.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert contract.functions.secondsPerPeriod().call() == token_economics.genesis_seconds_per_period

    tx = policy_manager.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = adjudicator.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setPolicyManager(policy_manager.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setAdjudicator(adjudicator.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWorkLock(worklock.address).transact()
    testerchain.wait_for_receipt(tx)

    current_period = contract.functions.getCurrentPeriod().call()
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 1
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 2

    # Initialize Escrow contract
    tx = token.functions.approve(contract.address, token_economics.erc20_reward_supply).transact()
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.initialize(token_economics.erc20_reward_supply, creator).transact()
    testerchain.wait_for_receipt(tx)

    # Prepare stakers
    stakers = (staker1, staker2, staker3, staker4, staker5, staker8)
    for staker in (*stakers, staker6):
        max_stake_size = token_economics.maximum_allowed_locked
        tx = token.functions.transfer(staker, max_stake_size).transact()
        testerchain.wait_for_receipt(tx)
        tx = token.functions.approve(contract.address, max_stake_size).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    first_period = contract.functions.getCurrentPeriod().call()
    if first_period % 2 == 1:
        testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
        first_period = contract.functions.getCurrentPeriod().call()

    # First staker: unlocked tokens, minted everything, forgot to withdraw before migration
    duration = token_economics.minimum_locked_periods
    stake_size = 3 * token_economics.minimum_allowed_locked
    tx = contract.functions.deposit(staker1, stake_size, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(staker1).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWindDown(True).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)

    # Second staker: almost unlocked tokens, last period - current and next one for two sub-stakes
    tx = contract.functions.deposit(staker2, stake_size, duration + 1).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.deposit(staker2, stake_size, duration + 2).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(staker2).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setReStake(False).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWindDown(True).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)

    # Third staker: active staker but with downtimes
    tx = contract.functions.deposit(staker3, stake_size, duration + 1).transact({'from': staker3})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(staker3).transact({'from': staker3})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setReStake(False).transact({'from': staker3})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWindDown(True).transact({'from': staker3})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.commitToNextPeriod().transact({'from': staker3})
    testerchain.wait_for_receipt(tx)

    # Fifth staker: like first one but also destroyed all info that could
    tx = contract.functions.deposit(staker5, stake_size, duration).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(staker5).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setReStake(False).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWindDown(True).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)

    # Special staker: prepare merged sub-stakes
    tx = contract.functions.deposit(staker8, stake_size, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.deposit(staker8, stake_size, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.mergeStake(0, 1).transact({'from': staker8})
    testerchain.wait_for_receipt(tx)

    for i in range(duration):
        tx = contract.functions.commitToNextPeriod().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
        tx = contract.functions.commitToNextPeriod().transact({'from': staker2})
        testerchain.wait_for_receipt(tx)
        tx = contract.functions.commitToNextPeriod().transact({'from': staker5})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(hours=token_economics.genesis_hours_per_period)

    tx = contract.functions.commitToNextPeriod().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    current_period = contract.functions.getCurrentPeriod().call()

    tx = contract.functions.mint().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getLockedTokens(staker1, 0).call() == 0
    assert contract.functions.getPastDowntimeLength(staker1).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker1).call() == current_period - 1

    tx = contract.functions.commitToNextPeriod().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getLockedTokens(staker2, 0).call() == 2 * stake_size
    assert contract.functions.getLockedTokens(staker2, 1).call() == stake_size
    assert contract.functions.getLockedTokens(staker2, 2).call() == 0
    assert contract.functions.getPastDowntimeLength(staker2).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker2).call() == current_period + 1

    tx = contract.functions.commitToNextPeriod().transact({'from': staker3})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getLockedTokens(staker3, 1).call() == stake_size
    assert contract.functions.getLockedTokens(staker3, 2).call() == stake_size
    assert contract.functions.getLockedTokens(staker3, 3).call() == 0
    assert contract.functions.getPastDowntimeLength(staker3).call() == 2
    assert contract.functions.getLastCommittedPeriod(staker3).call() == current_period + 1

    # Fourth staker: just deposited before migration
    tx = contract.functions.deposit(staker4, 2 * stake_size, 4 * duration).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(staker4).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.setWindDown(True).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getPastDowntimeLength(staker4).call() == 0
    assert contract.functions.getLastCommittedPeriod(staker4).call() == 0

    tx = contract.functions.mint().transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.removeUnusedSubStake(0).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(NULL_ADDRESS).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    stake_size_5 = contract.functions.getAllTokens(staker5).call()
    tx = contract.functions.withdraw(stake_size_5).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getLockedTokens(staker5, 0).call() == 0
    assert contract.functions.getPastDowntimeLength(staker5).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker5).call() == current_period - 1

    assert contract.functions.lockedPerPeriod(current_period).call() != 0
    current_minting_period = contract.functions.currentMintingPeriod().call()

    ##########
    # Deploy new version of the contract
    ##########
    deploy_args = token_economics.staking_deployment_parameters
    staking_escrow_library, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        policy_manager.address,
        adjudicator.address,
        worklock.address,
        *deploy_args)
    contract = testerchain.client.get_contract(
        abi=staking_escrow_library.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    migration_log = contract.events.Migrated.createFilter(fromBlock='latest')

    current_period = contract.functions.getCurrentPeriod().call()
    tx = dispatcher.functions.upgrade(staking_escrow_library.address).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.secondsPerPeriod().call() == token_economics.seconds_per_period
    assert contract.functions.genesisSecondsPerPeriod().call() == token_economics.genesis_seconds_per_period
    assert contract.functions.getCurrentPeriod().call() == current_period // 2
    assert contract.functions.lockedPerPeriod(current_period).call() == 0
    assert contract.functions.lockedPerPeriod(current_period - 1).call() == 0
    assert contract.functions.lockedPerPeriod(current_period + 1).call() == 0
    assert contract.functions.currentMintingPeriod().call() == current_minting_period // 2
    assert contract.functions.getActiveStakers(1, 0, 0).call() == [0, []]
    current_period = contract.functions.getCurrentPeriod().call()
    assert contract.functions.lockedPerPeriod(current_period).call() == 0
    assert contract.functions.lockedPerPeriod(current_period - 1).call() == 0
    assert contract.functions.lockedPerPeriod(current_period + 1).call() == 0

    # Staker can't do almost anything before migration
    for staker in stakers:
        assert contract.functions.getLockedTokens(staker, 0).call() == 0
        assert contract.functions.getLockedTokens(staker, 1).call() == 0
        _wind_down, _re_stake, _measure_work, _snapshots, migrated = contract.functions.getFlags(staker).call()
        assert not migrated
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.withdraw(1).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.bondWorker(NULL_ADDRESS).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.deposit(staker, stake_size, duration).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.lockAndCreate(stake_size, duration).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.depositAndIncrease(0, 1).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.lockAndIncrease(0, 1).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.divideStake(0, stake_size // 2, duration).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.prolongStake(0, duration).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.mergeStake(0, 1).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.removeUnusedSubStake(0).transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = contract.functions.mint().transact({'from': staker})
            testerchain.wait_for_receipt(tx)
        with pytest.raises((TransactionFailed, ValueError)):
            tx = adjudicator.functions.slashStaker(staker, 2, staker, 1).transact()
            testerchain.wait_for_receipt(tx)

    # Time to migrate
    ##########
    # Staker who has nothing
    ##########
    assert len(migration_log.get_all_entries()) == 0
    wind_down, re_stake, measure_work, snapshots, migrated = contract.functions.getFlags(staker5).call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.commitToNextPeriod().transact({'from': staker5})
        testerchain.wait_for_receipt(tx)

    tx = contract.functions.migrate(staker5).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getFlags(staker5).call() == [wind_down, re_stake, measure_work, snapshots, True]
    assert policy_manager.functions.migratedNodes(staker5).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker5).call() == 1
    assert contract.functions.getPastDowntimeLength(staker5).call() == 0
    assert contract.functions.getSubStakesLength(staker5).call() == 0
    assert contract.functions.getLockedTokens(staker5, 0).call() == 0
    staker_info = contract.functions.stakerInfo(staker5).call()[0:8]
    assert staker_info == [0, 0, 0, 1, 0, 0, (first_period + duration + 1) // 2, NULL_ADDRESS]

    tx = contract.functions.migrate(staker5).transact()
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.migratedNodes(staker5).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker5).call() == 1

    events = migration_log.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['staker'] == staker5
    assert event_args['period'] == current_period

    registrations = policy_manager.functions.getPeriodsLength(staker5).call()
    tx = contract.functions.deposit(staker5, stake_size, duration).transact({'from': staker5})
    testerchain.wait_for_receipt(tx)
    _wind_down, _re_stake, _measure_work, _snapshots, migrated = contract.functions.getFlags(staker5).call()
    assert migrated
    assert policy_manager.functions.getPeriodsLength(staker5).call() == registrations

    ##########
    # Staker that finished staking but did not call withdraw before migration
    ##########
    stake_1 = contract.functions.getAllTokens(staker1).call()
    wind_down, re_stake, measure_work, snapshots, migrated = contract.functions.getFlags(staker1).call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.commitToNextPeriod().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    tx = contract.functions.migrate(staker1).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getFlags(staker1).call() == [wind_down, re_stake, measure_work, snapshots, True]
    assert policy_manager.functions.migratedNodes(staker1).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker1).call() == 1
    assert contract.functions.getPastDowntimeLength(staker1).call() == 0
    assert contract.functions.getSubStakesLength(staker1).call() == 1
    sub_stake = contract.functions.getSubStakeInfo(staker1, 0).call()
    last_period_mod = (first_period + duration) % 2
    assert sub_stake == [(first_period + 1) // 2, (first_period + duration) // 2, 0, stake_1]
    assert contract.functions.getLockedTokens(staker1, 0).call() == 0 if last_period_mod == 1 else stake_1
    assert contract.functions.getLockedTokens(staker1, 1).call() == 0
    staker_info = contract.functions.stakerInfo(staker1).call()[0:8]
    assert staker_info == [stake_1, 0, 0, 1, 0, 0, first_period // 2, staker1]

    tx = contract.functions.migrate(staker1).transact()
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.migratedNodes(staker1).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker1).call() == 1

    events = migration_log.get_all_entries()
    assert len(events) == 2
    event_args = events[1]['args']
    assert event_args['staker'] == staker1
    assert event_args['period'] == current_period

    ##########
    # Almost finished staker
    ##########
    stake_2 = contract.functions.getAllTokens(staker2).call()
    wind_down, re_stake, measure_work, snapshots, migrated = contract.functions.getFlags(staker2).call()

    tx = contract.functions.migrate(staker2).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getAllTokens(staker2).call() == stake_2

    assert contract.functions.getFlags(staker2).call() == [wind_down, re_stake, measure_work, snapshots, True]
    assert policy_manager.functions.migratedNodes(staker2).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker2).call() == 1
    assert contract.functions.getPastDowntimeLength(staker2).call() == 0
    assert contract.functions.getSubStakesLength(staker2).call() == 2
    sub_stake = contract.functions.getSubStakeInfo(staker2, 0).call()
    last_period_1 = (first_period + duration + 1) // 2
    assert sub_stake == [(first_period + 1) // 2, last_period_1, 0, stake_size]
    sub_stake = contract.functions.getSubStakeInfo(staker2, 1).call()
    last_period_2 = (first_period + duration + 2) // 2
    assert sub_stake == [(first_period + 1) // 2, last_period_2, 0, stake_size]
    assert contract.functions.getLockedTokens(staker2, 0).call() == 2 * stake_size
    assert contract.functions.getLockedTokens(staker2, 1).call() == stake_size
    assert contract.functions.getLockedTokens(staker2, 2).call() == 0
    staker_info = contract.functions.stakerInfo(staker2).call()[0:8]
    assert staker_info == [stake_2, 0, 0, 1, 0, 0, first_period // 2, staker2]

    tx = contract.functions.migrate(staker2).transact()
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.migratedNodes(staker2).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker2).call() == 1

    events = migration_log.get_all_entries()
    assert len(events) == 3
    event_args = events[2]['args']
    assert event_args['staker'] == staker2
    assert event_args['period'] == current_period

    # Second staker can commit once in one case
    tx = contract.functions.commitToNextPeriod().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.lockedPerPeriod(current_period).call() == 0
    assert contract.functions.lockedPerPeriod(current_period + 1).call() == stake_size
    assert contract.functions.getLastCommittedPeriod(staker2).call() == current_period + 1
    assert contract.functions.getPastDowntimeLength(staker2).call() == 1
    assert contract.functions.getPastDowntime(staker2, 0).call() == [2, current_period]
    sub_stake = contract.functions.getSubStakeInfo(staker2, 0).call()
    assert sub_stake == [(first_period + 1) // 2, last_period_1, 0, stake_size]
    sub_stake = contract.functions.getSubStakeInfo(staker2, 1).call()
    assert sub_stake == [(first_period + 1) // 2, last_period_2, 0, stake_size]
    assert contract.functions.getLockedTokens(staker2, 0).call() == 2 * stake_size
    assert contract.functions.getLockedTokens(staker2, 1).call() == stake_size
    assert contract.functions.getLockedTokens(staker2, 2).call() == 0
    staker_info = contract.functions.stakerInfo(staker2).call()[0:8]
    assert staker_info == [stake_2, 0, current_period + 1, 1, 0, 0, first_period // 2, staker2]

    tx = adjudicator.functions.slashStaker(staker2, 2, staker2, 1).transact()
    testerchain.wait_for_receipt(tx)

    ##########
    # Active staker with downtimes
    ##########
    testerchain.time_travel(periods=1, periods_base=token_economics.seconds_per_period)
    current_period = contract.functions.getCurrentPeriod().call()

    stake_3 = contract.functions.getAllTokens(staker3).call()
    wind_down, re_stake, measure_work, snapshots, migrated = contract.functions.getFlags(staker3).call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.commitToNextPeriod().transact({'from': staker3})
        testerchain.wait_for_receipt(tx)

    tx = contract.functions.migrate(staker3).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getAllTokens(staker3).call() == stake_3

    assert contract.functions.getFlags(staker3).call() == [wind_down, re_stake, measure_work, snapshots, True]
    assert policy_manager.functions.migratedNodes(staker3).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker3).call() == 1
    assert contract.functions.getPastDowntimeLength(staker3).call() == 0
    assert contract.functions.getSubStakesLength(staker3).call() == 1
    sub_stake = contract.functions.getSubStakeInfo(staker3, 0).call()
    assert sub_stake == [(first_period + 1) // 2, current_period, 0, stake_size]
    assert contract.functions.getLockedTokens(staker3, 0).call() == stake_size
    assert contract.functions.getLockedTokens(staker3, 1).call() == 0
    staker_info = contract.functions.stakerInfo(staker3).call()[0:8]
    assert staker_info == [stake_3, 0, 0, 1, 0, 0, first_period // 2, staker3]

    tx = contract.functions.migrate(staker3).transact()
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.migratedNodes(staker3).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker3).call() == 1

    events = migration_log.get_all_entries()
    assert len(events) == 4
    event_args = events[3]['args']
    assert event_args['staker'] == staker3
    assert event_args['period'] == current_period

    ##########
    # Semi-fresh staker
    ##########

    stake_4 = contract.functions.getAllTokens(staker4).call()
    wind_down, re_stake, measure_work, snapshots, migrated = contract.functions.getFlags(staker4).call()
    tx = contract.functions.commitToNextPeriod().transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getAllTokens(staker4).call() == stake_4

    assert contract.functions.getFlags(staker4).call() == [wind_down, re_stake, measure_work, snapshots, True]
    assert policy_manager.functions.migratedNodes(staker4).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker4).call() == current_period + 1
    assert contract.functions.getPastDowntimeLength(staker4).call() == 1
    assert contract.functions.getPastDowntime(staker4, 0).call() == [2, current_period]
    assert contract.functions.getSubStakesLength(staker4).call() == 1
    sub_stake = contract.functions.getSubStakeInfo(staker4, 0).call()
    assert sub_stake == [(first_period + 4) // 2, 0, 2 * duration - 1, 2 * stake_size]
    assert contract.functions.getLockedTokens(staker4, 0).call() == 2 * stake_size
    assert contract.functions.getLockedTokens(staker4, 1).call() == 2 * stake_size
    assert contract.functions.getLockedTokens(staker4, 2).call() == 2 * stake_size
    staker_info = contract.functions.stakerInfo(staker4).call()[0:8]
    assert staker_info == [stake_4, 0, current_period + 1, 1, 0, 0, (first_period + 3) // 2, staker4]

    tx = contract.functions.migrate(staker4).transact()
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.migratedNodes(staker4).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker4).call() == current_period + 1

    events = migration_log.get_all_entries()
    assert len(events) == 5
    event_args = events[4]['args']
    assert event_args['staker'] == staker4
    assert event_args['period'] == current_period

    tx = contract.functions.divideStake(0, stake_size, 1).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.prolongStake(0, 1).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.mergeStake(0, 1).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.removeUnusedSubStake(1).transact({'from': staker4})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getSubStakesLength(staker4).call() == 1
    sub_stake = contract.functions.getSubStakeInfo(staker4, 0).call()
    assert sub_stake == [(first_period + 4) // 2, 0, 2 * duration, 2 * stake_size]

    ##########
    # Fresh staker
    ##########

    # Only staker can call migrate()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.migrate(staker6).transact({'from': staker6})
        testerchain.wait_for_receipt(tx)

    registrations = policy_manager.functions.getPeriodsLength(staker6).call()
    assert registrations == 0
    tx = contract.functions.deposit(staker6, stake_size, duration).transact({'from': staker6})
    testerchain.wait_for_receipt(tx)
    *other_flags, migrated = contract.functions.getFlags(staker6).call()
    assert migrated
    assert contract.functions.getSubStakesLength(staker6).call() == 1
    sub_stake = contract.functions.getSubStakeInfo(staker6, 0).call()
    assert sub_stake == [current_period + 1, 0, duration, stake_size]
    staker_info = contract.functions.stakerInfo(staker6).call()[0:8]
    assert staker_info == [stake_size, 0, 0, 0, 0, 0, 0, NULL_ADDRESS]
    registrations = policy_manager.functions.getPeriodsLength(staker6).call()
    assert registrations == 1
    tx = contract.functions.migrate(staker6).transact({'from': staker6})
    testerchain.wait_for_receipt(tx)
    assert policy_manager.functions.migratedNodes(staker6).call() == 0

    ##########
    # Fresh WorkLock staker
    ##########
    tx = token.functions.transfer(worklock.address, stake_size).transact()
    testerchain.wait_for_receipt(tx)
    registrations = policy_manager.functions.getPeriodsLength(staker7).call()
    assert registrations == 0
    tx = worklock.functions.depositFromWorkLock(staker7, stake_size, 2 * duration + 1).transact()
    testerchain.wait_for_receipt(tx)
    *other_flags, migrated = contract.functions.getFlags(staker7).call()
    assert migrated
    assert contract.functions.getSubStakesLength(staker7).call() == 1
    sub_stake = contract.functions.getSubStakeInfo(staker7, 0).call()
    assert sub_stake == [current_period + 1, 0, duration, stake_size]
    staker_info = contract.functions.stakerInfo(staker7).call()[0:8]
    assert staker_info == [stake_size, 0, 0, 0, 0, 0, 0, NULL_ADDRESS]
    registrations = policy_manager.functions.getPeriodsLength(staker7).call()
    assert registrations == 1
    assert policy_manager.functions.migratedNodes(staker7).call() == 0

    ##########
    # Special staker with merged sub-stakes
    ##########
    stake_8 = contract.functions.getAllTokens(staker8).call()
    wind_down, re_stake, measure_work, snapshots, migrated = contract.functions.getFlags(staker8).call()
    sub_stake = contract.functions.getSubStakeInfo(staker8, 1).call()
    assert sub_stake == [first_period + 1, 1, 0, stake_size]

    tx = contract.functions.migrate(staker8).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.getAllTokens(staker8).call() == stake_8

    assert contract.functions.getFlags(staker8).call() == [wind_down, re_stake, measure_work, snapshots, True]
    assert policy_manager.functions.migratedNodes(staker8).call() == 1
    assert contract.functions.getLastCommittedPeriod(staker8).call() == 1
    assert contract.functions.getPastDowntimeLength(staker8).call() == 0
    assert contract.functions.getSubStakesLength(staker8).call() == 2
    sub_stake = contract.functions.getSubStakeInfo(staker8, 0).call()
    assert sub_stake == [(first_period + 1) // 2, 0, duration // 2, 2 * stake_size]
    sub_stake = contract.functions.getSubStakeInfo(staker8, 1).call()
    assert sub_stake == [(first_period + 1) // 2, 1, 0, stake_size]
    assert contract.functions.getLockedTokens(staker8, 0).call() == 2 * stake_size
    assert contract.functions.getLockedTokens(staker8, 1).call() == 2 * stake_size
    staker_info = contract.functions.stakerInfo(staker8).call()[0:8]
    assert staker_info == [stake_8, 0, 0, 1, 0, 0, 0, NULL_ADDRESS]

    # Time machine test
    testerchain.time_travel(periods=1, periods_base=token_economics.seconds_per_period)
    current_period = contract.functions.getCurrentPeriod().call()
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 1
    testerchain.time_travel(hours=token_economics.hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 2

    # More tests
    tx = contract.functions.withdraw(1).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.removeUnusedSubStake(0).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.bondWorker(everyone_else[0]).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.withdraw(1).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.commitToNextPeriod().transact({'from': staker2})
        testerchain.wait_for_receipt(tx)

    assert len(migration_log.get_all_entries()) == 6

    ##########
    # Upgrade again
    ##########
    tx = dispatcher.functions.upgrade(staking_escrow_library.address).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.genesisSecondsPerPeriod().call() == token_economics.genesis_seconds_per_period
    assert contract.functions.secondsPerPeriod().call() == token_economics.seconds_per_period

    policy_manager, _ = deploy_contract(
        'PolicyManagerForStakingEscrowMock', NULL_ADDRESS, 2 * token_economics.seconds_per_period
    )
    deploy_args = token_economics.staking_deployment_parameters
    deploy_args = (token_economics.hours_per_period,
                   2 * token_economics.hours_per_period,
                   *deploy_args[2:])
    staking_escrow_2_library, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        policy_manager.address,
        adjudicator.address,
        worklock.address,
        *deploy_args)
    current_period = contract.functions.getCurrentPeriod().call()
    tx = dispatcher.functions.upgrade(staking_escrow_2_library.address).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.genesisSecondsPerPeriod().call() == token_economics.seconds_per_period
    assert contract.functions.secondsPerPeriod().call() == 2 * token_economics.seconds_per_period
    assert contract.functions.getCurrentPeriod().call() == current_period // 2
