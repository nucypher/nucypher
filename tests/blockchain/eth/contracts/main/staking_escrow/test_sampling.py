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

from nucypher.blockchain.eth.interfaces import BlockchainInterface

@pytest.mark.slow
def test_sampling(testerchain, token, escrow_contract):
    escrow = escrow_contract(5 * 10 ** 8)
    creator = testerchain.etherbase_account

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    stakers = testerchain.stakers_accounts
    amount = token.functions.balanceOf(creator).call() // 2
    largest_locked = amount

    # Airdrop
    for staker in stakers:
        tx = token.functions.transfer(staker, amount).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
        amount = amount // 2

    # Can't use sample without points, with zero periods value, or not sorted in ascending order.
    with pytest.raises(TransactionFailed):
        escrow.functions.sample([], 1).call()
    with pytest.raises(TransactionFailed):
        escrow.functions.sample([1], 0).call()
    with pytest.raises(TransactionFailed):
        escrow.functions.sample([3, 2, 1], 0).call()

    # No stakers yet
    addresses = escrow.functions.sample([1], 1).call()
    assert 1 == len(addresses)
    assert BlockchainInterface.NULL_ADDRESS == addresses[0]

    all_locked_tokens = 0
    # All stakers lock tokens for different lock periods
    for index, staker in enumerate(stakers):
        balance = token.functions.balanceOf(staker).call()
        tx = token.functions.approve(escrow.address, balance).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.deposit(balance, index + 2).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.setWorker(staker).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.confirmActivity().transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        all_locked_tokens += balance

    # Stakers are active starting from the next period
    assert 0 == escrow.functions.getAllLockedTokens(1).call()

    # So sampling in current period is useless
    addresses = escrow.functions.sample([1], 1).call()
    assert 1 == len(addresses)
    assert BlockchainInterface.NULL_ADDRESS == addresses[0]

    # Wait next period and check all locked tokens
    testerchain.time_travel(hours=1)
    assert all_locked_tokens == escrow.functions.getAllLockedTokens(1).call()
    assert all_locked_tokens > escrow.functions.getAllLockedTokens(2).call()
    assert 0 < escrow.functions.getAllLockedTokens(len(stakers)).call()
    assert 0 == escrow.functions.getAllLockedTokens(len(stakers) + 1).call()

    # All stakers confirm activity
    for staker in stakers:
        tx = escrow.functions.confirmActivity().transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Sample one staker by value less than first staker's stake
    addresses = escrow.functions.sample([largest_locked - 1], 1).call()
    assert 1 == len(addresses)
    assert stakers[0] == addresses[0]

    # Sample two stakers by values that are equal to first and second stakes
    # In the result must be second and third stakers because of strict condition in the sampling
    addresses = escrow.functions.sample([largest_locked, largest_locked + largest_locked // 2], 1).call()
    assert 2 == len(addresses)
    assert stakers[1] == addresses[0]
    assert stakers[2] == addresses[1]

    # Sample two stakers by values that within first and second stakes
    # In the result must be second and third stakers because of strict condition in the sampling
    # sumOfLockedTokens > point
    addresses = escrow.functions.sample([largest_locked - 1, largest_locked + 1], 1).call()
    assert 2 == len(addresses)
    assert stakers[0] == addresses[0]
    assert stakers[1] == addresses[1]

    # Sample staker by the max duration of the longest stake
    # The result is the staker who has the longest stake
    addresses = escrow.functions.sample([1], len(stakers)).call()
    assert 1 == len(addresses)
    assert stakers[-1] == addresses[0]

    # Sample staker using the duration more than the longest stake
    # The result is empty
    addresses = escrow.functions.sample([1], len(stakers) + 1).call()
    assert 1 == len(addresses)
    assert BlockchainInterface.NULL_ADDRESS == addresses[0]

    # Sample stakers by different durations and minimum value
    # Each result is the first appropriate stake by length
    for index, _ in enumerate(stakers[:-1], start=1):
        addresses = escrow.functions.sample([1], index + 1).call()
        assert 1 == len(addresses)
        assert stakers[index] == addresses[0]

    # Sample all stakers by values as stake minus one
    # The result must contain all stakers
    points = [escrow.functions.getLockedTokens(staker).call() for staker in stakers]
    points[0] = points[0] - 1
    for i in range(1, len(points)):
        points[i] += points[i-1]
    addresses = escrow.functions.sample(points, 1).call()
    assert stakers == addresses

    # Test stakers iteration
    assert len(stakers) == escrow.functions.getStakersLength().call()
    for index, staker in enumerate(stakers):
        assert stakers[index] == escrow.functions.stakers(index).call()
