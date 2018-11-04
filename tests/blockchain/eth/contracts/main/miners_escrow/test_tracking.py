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
def test_sampling(testerchain, token, escrow_contract):
    escrow = escrow_contract(5 * 10 ** 8)
    NULL_ADDR = '0x' + '0' * 40
    creator = testerchain.interface.w3.eth.accounts[0]

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    miners = testerchain.interface.w3.eth.accounts[1:]
    amount = token.functions.balanceOf(creator).call() // 2
    largest_locked = amount

    # Airdrop
    for miner in miners:
        tx = token.functions.transfer(miner, amount).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
        amount = amount // 2

    # Cant't use sample without points or with zero periods value
    with pytest.raises((TransactionFailed, ValueError)):
        escrow.functions.sample([], 1).call()
    with pytest.raises((TransactionFailed, ValueError)):
        escrow.functions.sample([1], 0).call()

    # No miners yet
    addresses = escrow.functions.sample([1], 1).call()
    assert 1 == len(addresses)
    assert NULL_ADDR == addresses[0]

    all_locked_tokens = 0
    # All miners lock tokens for different duration
    for index, miner in enumerate(miners):
        balance = token.functions.balanceOf(miner).call()
        tx = token.functions.approve(escrow.address, balance).transact({'from': miner})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.deposit(balance, index + 2).transact({'from': miner})
        testerchain.wait_for_receipt(tx)
        all_locked_tokens += balance

    # Miners are active from the next period
    assert 0 == escrow.functions.getAllLockedTokens(1).call()

    # So sampling in current period is useless
    addresses = escrow.functions.sample([1], 1).call()
    assert 1 == len(addresses)
    assert NULL_ADDR == addresses[0]

    # Wait next period and check all locked tokens
    testerchain.time_travel(hours=1)
    assert all_locked_tokens == escrow.functions.getAllLockedTokens(1).call()
    assert all_locked_tokens > escrow.functions.getAllLockedTokens(2).call()
    assert 0 < escrow.functions.getAllLockedTokens(len(miners)).call()
    assert 0 == escrow.functions.getAllLockedTokens(len(miners) + 1).call()

    # All miners confirm activity
    for miner in miners:
        tx = escrow.functions.confirmActivity().transact({'from': miner})
        testerchain.wait_for_receipt(tx)

    # Sample one miner by value less than first miner's stake
    addresses = escrow.functions.sample([all_locked_tokens // 3], 1).call()
    assert 1 == len(addresses)
    assert miners[0] == addresses[0]

    # Sample two miners by values that are equal to first and second miners stakes
    # In the result must be second and third miners because of strict condition in the sampling
    # sumOfLockedTokens > point
    addresses = escrow.functions.sample([largest_locked, largest_locked // 2], 1).call()
    assert 2 == len(addresses)
    assert miners[1] == addresses[0]
    assert miners[2] == addresses[1]

    # Sample miner by the max duration of the longest stake
    # The result is the miner who has the longest stake
    addresses = escrow.functions.sample([1], len(miners)).call()
    assert 1 == len(addresses)
    assert miners[-1] == addresses[0]
    # Sample miner by the duration more than the longest stake
    # The result is empty
    addresses = escrow.functions.sample([1], len(miners) + 1).call()
    assert 1 == len(addresses)
    assert NULL_ADDR == addresses[0]

    # Sample by values that more than all locked tokens
    # Only one miner will be in the result
    addresses = escrow.functions.sample([largest_locked, largest_locked], 1).call()
    assert 2 == len(addresses)
    assert miners[1] == addresses[0]
    assert NULL_ADDR == addresses[1]

    # Sample miners by different durations and minimum value
    # Each result is the first appropriate stake by length
    for index, _ in enumerate(miners[:-1], start=1):
        addresses = escrow.functions.sample([1], index + 1).call()
        assert 1 == len(addresses)
        assert miners[index] == addresses[0]

    # Sample all miners by values as stake minus one
    # The result must contain all miners because of condition sumOfLockedTokens > point
    points = [escrow.functions.getLockedTokens(miner).call() for miner in miners]
    points[0] = points[0] - 1
    addresses = escrow.functions.sample(points, 1).call()
    assert miners == addresses

    # Test miners iteration
    assert len(miners) == escrow.functions.getMinersLength().call()
    for index, miner in enumerate(miners):
        assert miners[index] == escrow.functions.miners(index).call()


@pytest.mark.slow
def test_pre_deposit(testerchain, token, escrow_contract):
    escrow = escrow_contract(1500)
    policy_manager_interface = testerchain.interface.get_contract_factory('PolicyManagerForMinersEscrowMock')
    policy_manager = testerchain.interface.w3.eth.contract(
        abi=policy_manager_interface.abi,
        address=escrow.functions.policyManager().call(),
        ContractFactoryClass=Contract)
    creator = testerchain.interface.w3.eth.accounts[0]

    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')

    # Initialize Escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.functions.approve(escrow.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Deposit tokens for 1 miner
    owner = testerchain.interface.w3.eth.accounts[1]
    tx = escrow.functions.preDeposit([owner], [1000], [10]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 1000 == escrow.functions.minerInfo(owner).call()[VALUE_FIELD]
    assert 0 == escrow.functions.getLockedTokens(owner).call()
    assert 1000 == escrow.functions.getLockedTokens(owner, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(owner, 10).call()
    assert 0 == escrow.functions.getLockedTokens(owner, 11).call()
    period = escrow.functions.getCurrentPeriod().call()
    assert 1 == policy_manager.functions.getPeriodsLength(owner).call()
    assert period == policy_manager.functions.getPeriod(owner, 0).call()
    assert 0 == escrow.functions.getPastDowntimeLength(owner).call()
    assert 0 == escrow.functions.getLastActivePeriod(owner).call()

    # Can't pre-deposit tokens again for the same miner twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([testerchain.interface.w3.eth.accounts[1]], [1000], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't pre-deposit tokens with too low or too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([testerchain.interface.w3.eth.accounts[2]], [1], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([testerchain.interface.w3.eth.accounts[2]], [1501], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([testerchain.interface.w3.eth.accounts[2]], [500], [1])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Deposit tokens for multiple miners
    miners = testerchain.interface.w3.eth.accounts[2:7]
    tx = escrow.functions.preDeposit(
        miners, [100, 200, 300, 400, 500], [50, 100, 150, 200, 250]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    assert 2500 == token.functions.balanceOf(escrow.address).call()
    period = escrow.functions.getCurrentPeriod().call()
    for index, owner in enumerate(miners):
        assert 100 * (index + 1) == escrow.functions.minerInfo(owner).call()[VALUE_FIELD]
        assert 100 * (index + 1) == escrow.functions.getLockedTokens(owner, 1).call()
        assert 100 * (index + 1) == escrow.functions.getLockedTokens(owner, 50 * (index + 1)).call()
        assert 0 == escrow.functions.getLockedTokens(owner, 50 * (index + 1) + 1).call()
        assert 1 == policy_manager.functions.getPeriodsLength(owner).call()
        assert period == policy_manager.functions.getPeriod(owner, 0).call()
        assert 0 == escrow.functions.getPastDowntimeLength(owner).call()
        assert 0 == escrow.functions.getLastActivePeriod(owner).call()

    events = deposit_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[0]['args']
    assert testerchain.interface.w3.eth.accounts[1] == event_args['miner']
    assert 1000 == event_args['value']
    assert 10 == event_args['periods']
    event_args = events[1]['args']
    assert miners[0] == event_args['miner']
    assert 100 == event_args['value']
    assert 50 == event_args['periods']
    event_args = events[2]['args']
    assert miners[1] == event_args['miner']
    assert 200 == event_args['value']
    assert 100 == event_args['periods']
    event_args = events[3]['args']
    assert miners[2] == event_args['miner']
    assert 300 == event_args['value']
    assert 150 == event_args['periods']
    event_args = events[4]['args']
    assert miners[3] == event_args['miner']
    assert 400 == event_args['value']
    assert 200 == event_args['periods']
    event_args = events[5]['args']
    assert miners[4] == event_args['miner']
    assert 500 == event_args['value']
    assert 250 == event_args['periods']