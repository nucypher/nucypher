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

    # Ursula can't use method from Issuer contract directly, only from mint() method
    with pytest.raises(Exception):
        tx = escrow.functions.mint(1, 1, 1, 1).transact({'from': ursula1})
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
