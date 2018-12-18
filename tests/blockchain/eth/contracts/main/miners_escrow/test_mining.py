"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract

VALUE_FIELD = 0
DECIMALS_FIELD = 1
CONFIRMED_PERIOD_1_FIELD = 2
CONFIRMED_PERIOD_2_FIELD = 3
LAST_ACTIVE_PERIOD_FIELD = 4


@pytest.mark.slow
def test_mining(testerchain, token, escrow_contract):
    escrow = escrow_contract(1500)
    policy_manager_interface = testerchain.interface.get_contract_factory('PolicyManagerForMinersEscrowMock')
    policy_manager = testerchain.interface.w3.eth.contract(
        abi=policy_manager_interface.abi,
        address=escrow.functions.policyManager().call(),
        ContractFactoryClass=Contract)
    creator = testerchain.interface.w3.eth.accounts[0]
    ursula1 = testerchain.interface.w3.eth.accounts[1]
    ursula2 = testerchain.interface.w3.eth.accounts[2]

    mining_log = escrow.events.Mined.createFilter(fromBlock='latest')
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    divides_log = escrow.events.Divided.createFilter(fromBlock='latest')
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Give Ursula and Ursula(2) some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(ursula2, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.mint().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 2000).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 750).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(500, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    # Check parameters in call of the policy manager mock
    period = escrow.functions.getCurrentPeriod().call()
    assert 1 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 1 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period == policy_manager.functions.getPeriod(ursula1, 0).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 0).call()
    # Check downtime parameters
    assert 1 == escrow.functions.getPastDowntimeLength(ursula1).call()
    downtime = escrow.functions.getPastDowntime(ursula1, 0).call()
    assert 1 == downtime[0]
    assert period == downtime[1]
    assert 1 == escrow.functions.getPastDowntimeLength(ursula2).call()
    downtime = escrow.functions.getPastDowntime(ursula2, 0).call()
    assert 1 == downtime[0]
    assert period == downtime[1]
    assert period + 1 == escrow.functions.getLastActivePeriod(ursula1).call()
    assert period + 1 == escrow.functions.getLastActivePeriod(ursula2).call()

    # Ursula divides her stake
    tx = escrow.functions.divideStake(0, 500, 1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    # Can't use methods from Issuer contract directly
    with pytest.raises(Exception):
        tx = escrow.functions.mint(1, 1, 1, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises(Exception):
        tx = escrow.functions.unMint(1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Only Ursula confirms next period
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})

    testerchain.wait_for_receipt(tx)
    assert 1 == escrow.functions.getPastDowntimeLength(ursula1).call()

    # Checks that no error from repeated method call
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    # Ursula and Ursula(2) mint tokens for last periods
    # And only Ursula confirm activity for next period
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    period = escrow.functions.getCurrentPeriod().call()
    # Check result of mining
    assert 1046 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 525 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
    # Check that downtime value has not changed
    assert 1 == escrow.functions.getPastDowntimeLength(ursula1).call()
    assert 1 == escrow.functions.getPastDowntimeLength(ursula2).call()
    assert period + 1 == escrow.functions.getLastActivePeriod(ursula1).call()
    assert period - 1 == escrow.functions.getLastActivePeriod(ursula2).call()

    events = mining_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['miner']
    assert 46 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']
    event_args = events[1]['args']
    assert ursula2 == event_args['miner']
    assert 25 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    # Check parameters in call of the policy manager mock
    assert 2 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 2 == policy_manager.functions.getPeriodsLength(ursula2).call()
    period = escrow.functions.getCurrentPeriod().call() - 1
    assert period == policy_manager.functions.getPeriod(ursula1, 1).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 1).call()

    # Ursula tries to mint again and doesn't receive a reward
    # There are no more confirmed periods that are ready to mint
    tx = escrow.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1046 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    events = mining_log.get_all_entries()
    assert 2 == len(events)

    # Ursula can't confirm next period because stake is unlocked in current period
    testerchain.time_travel(hours=1)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    # But Ursula(2) can
    period = escrow.functions.getCurrentPeriod().call()
    assert period - 2 == escrow.functions.getLastActivePeriod(ursula2).call()
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    assert period + 1 == escrow.functions.getLastActivePeriod(ursula2).call()
    assert 2 == escrow.functions.getPastDowntimeLength(ursula2).call()
    downtime = escrow.functions.getPastDowntime(ursula2, 1).call()
    assert period - 1 == downtime[0]
    assert period == downtime[1]

    # Ursula mints tokens
    testerchain.time_travel(hours=1)
    tx = escrow.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    # But Ursula(2) can't get reward because she did not confirm activity
    tx = escrow.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 525 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]

    events = mining_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['miner']
    assert 106 == event_args['value']
    assert period == event_args['period']

    assert 4 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 2 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period - 1 == policy_manager.functions.getPeriod(ursula1, 2).call()
    assert period == policy_manager.functions.getPeriod(ursula1, 3).call()

    # Ursula(2) mints tokens
    testerchain.time_travel(hours=1)
    tx = escrow.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 575 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]

    events = mining_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula2 == event_args['miner']
    assert 50 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    period = escrow.functions.getCurrentPeriod().call() - 1
    assert 4 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 3 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 2).call()

    # Ursula(2) can't more confirm activity because stake is unlocked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)

    # Ursula can't confirm and get reward because no locked tokens
    tx = escrow.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    period = escrow.functions.getCurrentPeriod().call()
    assert period - 2 == escrow.functions.getLastActivePeriod(ursula1).call()
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    # Ursula still can't confirm activity
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula(2) deposits and locks more tokens
    tx = escrow.functions.deposit(250, 4).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.lock(500, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    assert 3 == escrow.functions.getPastDowntimeLength(ursula2).call()
    downtime = escrow.functions.getPastDowntime(ursula2, 2).call()
    assert period == downtime[0]
    assert period == downtime[1]

    # Ursula(2) mints only one period (by using deposit/approveAndCall function)
    testerchain.time_travel(hours=5)
    period = escrow.functions.getCurrentPeriod().call()
    assert period - 4 == escrow.functions.getLastActivePeriod(ursula2).call()
    tx = token.functions.approveAndCall(escrow.address, 100, testerchain.interface.w3.toBytes(2))\
        .transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 1025 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
    assert 4 == escrow.functions.getPastDowntimeLength(ursula2).call()
    downtime = escrow.functions.getPastDowntime(ursula2, 3).call()
    assert period - 3 == downtime[0]
    assert period == downtime[1]

    assert 4 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period - 4 == policy_manager.functions.getPeriod(ursula2, 3).call()

    events = mining_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert ursula2 == event_args['miner']
    assert 100 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    # Ursula(2) confirms activity for remaining periods
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 4 == escrow.functions.getPastDowntimeLength(ursula2).call()
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Ursula(2) withdraws all
    testerchain.time_travel(hours=2)
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    tx = escrow.functions.withdraw(1083).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 0 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
    assert 10233 == token.functions.balanceOf(ursula2).call()

    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula2 == event_args['miner']
    assert 1083 == event_args['value']

    assert 4 == len(deposit_log.get_all_entries())
    assert 6 == len(lock_log.get_all_entries())
    assert 1 == len(divides_log.get_all_entries())
    assert 10 == len(activity_log.get_all_entries())


@pytest.mark.slow
def test_slashing(testerchain, token, escrow_contract):
    escrow = escrow_contract(1500)
    overseer, _ = testerchain.interface.deploy_contract(
        'ChallengeOverseerForMinersEscrowMock', escrow.address
    )
    tx = escrow.functions.setChallengeOverseer(overseer.address).transact()
    testerchain.wait_for_receipt(tx)
    creator = testerchain.interface.w3.eth.accounts[0]
    ursula = testerchain.interface.w3.eth.accounts[1]
    investigator = testerchain.interface.w3.eth.accounts[2]

    slashing_log = escrow.events.Slashed.createFilter(fromBlock='latest')

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Give Ursula deposit some tokens
    tx = token.functions.transfer(ursula, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period = escrow.functions.getCurrentPeriod().call()
    assert 100 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 100 == escrow.functions.getLockedTokens(ursula).call()
    assert 100 == escrow.functions.lockedPerPeriod(period).call()
    assert 0 == escrow.functions.lockedPerPeriod(period + 1).call()

    # Can't slash directly using the escrow contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.slashMiner(ursula, 100, investigator, 10).transact()
        testerchain.wait_for_receipt(tx)
    # Penalty must be greater than zero
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.slashMiner(ursula, 0, investigator, 0).transact()
        testerchain.wait_for_receipt(tx)

    # Slash the whole stake
    reward = escrow.functions.getReservedReward().call()
    tx = overseer.functions.slashMiner(ursula, 100, investigator, 10).transact()
    testerchain.wait_for_receipt(tx)
    # Miner has no more sub stakes
    assert 0 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 0 == escrow.functions.getLockedTokens(ursula).call()
    assert 10 == token.functions.balanceOf(investigator).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()
    assert reward + 90 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula == event_args['miner']
    assert 100 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 10 == event_args['reward']

    # New deposit and confirmation of activity
    tx = escrow.functions.deposit(100, 5).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period += 1
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 100 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 100 == escrow.functions.getLockedTokens(ursula).call()
    assert 100 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 100 == escrow.functions.lockedPerPeriod(period).call()
    assert 100 == escrow.functions.lockedPerPeriod(period + 1).call()

    # Slash part of one sub stake (there is only one sub stake)
    reward = escrow.functions.getReservedReward().call()
    tx = overseer.functions.slashMiner(ursula, 10, investigator, 11).transact()
    testerchain.wait_for_receipt(tx)
    assert 90 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 90 == escrow.functions.getLockedTokens(ursula).call()
    assert 90 == escrow.functions.getLockedTokens(ursula, 1).call()
    # The reward will be equal to the penalty (can't be more then penalty)
    assert 20 == token.functions.balanceOf(investigator).call()
    assert 90 == escrow.functions.lockedPerPeriod(period).call()
    assert 90 == escrow.functions.lockedPerPeriod(period + 1).call()
    assert reward == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula == event_args['miner']
    assert 10 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 10 == event_args['reward']

    # New deposit of a longer sub stake
    tx = escrow.functions.deposit(100, 6).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    period += 1
    assert 90 == escrow.functions.getLockedTokens(ursula, -1).call()
    assert 190 == escrow.functions.getLockedTokens(ursula).call()
    assert 100 == escrow.functions.getLockedTokens(ursula, 4).call()
    assert 190 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 90 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 190 == escrow.functions.lockedPerPeriod(period).call()
    assert 0 == escrow.functions.lockedPerPeriod(period + 1).call()

    # Slash again part of the first sub stake because new sub stake is longer (there are two main sub stakes)
    reward = escrow.functions.getReservedReward().call()
    tx = overseer.functions.slashMiner(ursula, 10, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 180 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 90 == escrow.functions.getLockedTokens(ursula, -1).call()
    assert 180 == escrow.functions.getLockedTokens(ursula).call()
    assert 100 == escrow.functions.getLockedTokens(ursula, 4).call()
    assert 20 == token.functions.balanceOf(investigator).call()
    assert 90 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 180 == escrow.functions.lockedPerPeriod(period).call()
    assert reward + 10 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula == event_args['miner']
    assert 10 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # New deposit of a shorter sub stake
    tx = escrow.functions.deposit(110, 2).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    period += 2
    assert 290 == escrow.functions.getLockedTokens(ursula, -1).call()
    assert 290 == escrow.functions.getLockedTokens(ursula).call()
    assert 180 == escrow.functions.getLockedTokens(ursula, 2).call()
    deposit = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]  # Some reward is already mined
    assert 290 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()

    # Slash only free amount of tokens
    reward = escrow.functions.getReservedReward().call()
    tx = overseer.functions.slashMiner(ursula, deposit - 290, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 290 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 290 == escrow.functions.getLockedTokens(ursula, -1).call()
    assert 290 == escrow.functions.getLockedTokens(ursula).call()
    assert 180 == escrow.functions.getLockedTokens(ursula, 2).call()
    assert 20 == token.functions.balanceOf(investigator).call()
    assert 290 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()
    assert reward + deposit - 290 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula == event_args['miner']
    assert deposit - 290 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Slash only the new sub stake because it's the shortest one (there are three main sub stakes)
    tx = overseer.functions.slashMiner(ursula, 20, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 270 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 290 == escrow.functions.getLockedTokens(ursula, -1).call()
    assert 270 == escrow.functions.getLockedTokens(ursula).call()
    assert 180 == escrow.functions.getLockedTokens(ursula, 2).call()
    assert 20 == token.functions.balanceOf(investigator).call()
    assert 290 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()
    assert reward + deposit - 270 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert ursula == event_args['miner']
    assert 20 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Slash the whole new sub stake and part of the next shortest (there are three main sub stakes)
    reward = escrow.functions.getReservedReward().call()
    tx = overseer.functions.slashMiner(ursula, 100, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 170 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 290 == escrow.functions.getLockedTokens(ursula, -1).call()
    assert 170 == escrow.functions.getLockedTokens(ursula).call()
    assert 170 == escrow.functions.getLockedTokens(ursula, 2).call()
    assert 20 == token.functions.balanceOf(investigator).call()
    assert 290 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 0 == escrow.functions.lockedPerPeriod(period).call()
    assert reward + 100 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert ursula == event_args['miner']
    assert 100 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Confirmation of activity must handle correctly inactive sub stakes after slashing
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)

    # New deposit
    tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 170 == escrow.functions.getLockedTokens(ursula).call()
    assert 270 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 270 == escrow.functions.lockedPerPeriod(period + 1).call()
    deposit = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]  # Some reward is already mined
    unlocked_deposit = deposit - 270
    reward = escrow.functions.getReservedReward().call()

    # Slash the new sub stake which starts in the next period
    # Because locked value is more in the next period than in the current period
    tx = overseer.functions.slashMiner(ursula, unlocked_deposit + 10, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 170 == escrow.functions.getLockedTokens(ursula).call()
    assert 260 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 260 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 260 == escrow.functions.lockedPerPeriod(period + 1).call()
    assert reward + unlocked_deposit + 10 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    assert ursula == event_args['miner']
    assert unlocked_deposit + 10 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # After two periods two shortest sub stakes will be unlocked, lock again and slash after this
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)

    period += 2
    assert 260 == escrow.functions.getLockedTokens(ursula).call()
    assert 100 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula, 3).call()
    assert 260 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 260 == escrow.functions.lockedPerPeriod(period).call()
    assert 0 == escrow.functions.lockedPerPeriod(period + 1).call()
    tx = escrow.functions.lock(160, 2).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 260 == escrow.functions.getLockedTokens(ursula).call()
    assert 260 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula, 3).call()
    assert 260 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 260 == escrow.functions.lockedPerPeriod(period).call()
    assert 260 == escrow.functions.lockedPerPeriod(period + 1).call()
    deposit = escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]  # Some reward is already mined
    unlocked_deposit = deposit - 260

    # Slash two sub stakes:
    # one which will be unlocked after current period and new sub stake
    reward = escrow.functions.getReservedReward().call()
    tx = overseer.functions.slashMiner(ursula, unlocked_deposit + 10, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 250 == escrow.functions.getLockedTokens(ursula).call()
    assert 250 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula, 3).call()
    assert 250 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 260 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 250 == escrow.functions.lockedPerPeriod(period).call()
    assert 250 == escrow.functions.lockedPerPeriod(period + 1).call()
    assert reward + unlocked_deposit + 10 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 8 == len(events)
    event_args = events[7]['args']
    assert ursula == event_args['miner']
    assert unlocked_deposit + 10 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Slash four sub stakes:
    # two that will be unlocked after current period, new sub stake and another short sub stake
    tx = overseer.functions.slashMiner(ursula, 90, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 160 == escrow.functions.getLockedTokens(ursula).call()
    assert 160 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula, 3).call()
    assert 160 == escrow.functions.minerInfo(ursula).call()[VALUE_FIELD]
    assert 260 == escrow.functions.lockedPerPeriod(period - 1).call()
    assert 160 == escrow.functions.lockedPerPeriod(period).call()
    assert 160 == escrow.functions.lockedPerPeriod(period + 1).call()
    assert reward + unlocked_deposit + 100 == escrow.functions.getReservedReward().call()

    events = slashing_log.get_all_entries()
    assert 9 == len(events)
    event_args = events[8]['args']
    assert ursula == event_args['miner']
    assert 90 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Prepare second Ursula for tests
    ursula2 = testerchain.interface.w3.eth.accounts[3]
    tx = token.functions.transfer(ursula2, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Two deposits in consecutive periods
    tx = escrow.functions.deposit(100, 4).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.deposit(100, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=2)
    assert 100 == escrow.functions.getLockedTokens(ursula2, -2).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, -1).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 1).call()

    # Slash one sub stake to set the last period of this sub stake to the previous period
    tx = overseer.functions.slashMiner(ursula2, 100, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 100 == escrow.functions.getLockedTokens(ursula2, -2).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, -1).call()
    assert 100 == escrow.functions.getLockedTokens(ursula2).call()
    assert 100 == escrow.functions.getLockedTokens(ursula2, 1).call()

    events = slashing_log.get_all_entries()
    assert 10 == len(events)
    event_args = events[9]['args']
    assert ursula2 == event_args['miner']
    assert 100 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Slash the first sub stake
    # and check that the second sub stake will not combine with the slashed amount of the first one
    tx = overseer.functions.slashMiner(ursula2, 50, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 100 == escrow.functions.getLockedTokens(ursula2, -2).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, -1).call()
    assert 50 == escrow.functions.getLockedTokens(ursula2).call()
    assert 50 == escrow.functions.getLockedTokens(ursula2, 1).call()

    events = slashing_log.get_all_entries()
    assert 11 == len(events)
    event_args = events[10]['args']
    assert ursula2 == event_args['miner']
    assert 50 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']

    # Prepare next case: new deposit is longer than previous sub stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.deposit(100, 3).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 50 == escrow.functions.getLockedTokens(ursula2).call()
    assert 150 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 100 == escrow.functions.getLockedTokens(ursula2, 2).call()

    # Withdraw all not locked tokens
    deposit = escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]  # Some reward is already mined
    unlocked_deposit = deposit - 150
    tx = escrow.functions.withdraw(unlocked_deposit).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Slash the previous sub stake
    # Stake in the current period should not change, because overflow starts from the next period
    tx = overseer.functions.slashMiner(ursula2, 10, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert 50 == escrow.functions.getLockedTokens(ursula2).call()
    assert 140 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 100 == escrow.functions.getLockedTokens(ursula2, 2).call()

    events = slashing_log.get_all_entries()
    assert 12 == len(events)
    event_args = events[11]['args']
    assert ursula2 == event_args['miner']
    assert 10 == event_args['penalty']
    assert investigator == event_args['investigator']
    assert 0 == event_args['reward']
