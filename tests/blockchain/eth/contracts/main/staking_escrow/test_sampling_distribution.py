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

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME


# TODO: #1288 - Consider moving this test out from regular CI workflow to a scheduled workflow (e.g., nightly)
# @pytest.mark.slow
@pytest.mark.skip("Until SAMPLES can be raised. See #1288")
def test_sampling_distribution(testerchain, token, deploy_contract):

    #
    # SETUP
    #

    max_allowed_locked_tokens = 5 * 10 ** 8
    _staking_coefficient = 2 * 10 ** 7
    contract, _ = deploy_contract(
        contract_name=STAKING_ESCROW_CONTRACT_NAME,
        _token=token.address,
        _hoursPerPeriod=1,
        _miningCoefficient=4 * _staking_coefficient,
        _lockedPeriodsCoefficient=4,
        _rewardedPeriods=4,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=100,
        _maxAllowableLockedTokens=max_allowed_locked_tokens,
        _minWorkerPeriods=1
    )

    policy_manager, _ = deploy_contract(
        'PolicyManagerForStakingEscrowMock', token.address, contract.address
    )
    tx = contract.functions.setPolicyManager(policy_manager.address).transact()
    testerchain.wait_for_receipt(tx)

    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(hours=1)

    escrow = contract
    creator = testerchain.etherbase_account

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    stakers = testerchain.stakers_accounts
    amount = token.functions.balanceOf(creator).call() // len(stakers)

    # Airdrop
    for staker in stakers:
        tx = token.functions.transfer(staker, amount).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    all_locked_tokens = len(stakers) * amount
    for staker in stakers:
        balance = token.functions.balanceOf(staker).call()
        tx = token.functions.approve(escrow.address, balance).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.deposit(balance, 10).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.setWorker(staker).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.confirmActivity().transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Wait next period and check all locked tokens
    testerchain.time_travel(hours=1)

    #
    # Test sampling distribution
    #

    ERROR_TOLERANCE = 0.05  # With this tolerance, all sampling ratios should between 5% and 15% (expected is 10%)
    SAMPLES = 100
    quantity = 3
    import random
    from collections import Counter

    counter = Counter()
    for i in range(SAMPLES):
        points = sorted(random.SystemRandom().randrange(all_locked_tokens) for _ in range(quantity))
        addresses = set(escrow.functions.sample(points, 1).call())
        addresses.discard(BlockchainInterface.NULL_ADDRESS)
        counter.update(addresses)

    total_times = sum(counter.values())

    expected = amount / all_locked_tokens
    for staker in stakers:
        times = counter[staker]
        sampled_ratio = times / total_times
        abs_error = abs(expected - sampled_ratio)
        assert abs_error < ERROR_TOLERANCE
