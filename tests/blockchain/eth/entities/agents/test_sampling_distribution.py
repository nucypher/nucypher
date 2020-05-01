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
from collections import Counter

from nucypher.blockchain.economics import BaseEconomics
from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS, STAKING_ESCROW_CONTRACT_NAME


@pytest.fixture()
def token_economics():
    economics = BaseEconomics(initial_supply=10 ** 9,
                              first_phase_supply=int(0.5 * 10 ** 9),
                              first_phase_stable_issuance=10 ** 6,
                              total_supply=2 * 10 ** 9,
                              second_phase_coefficient=10 ** 7,
                              locking_duration_coefficient_1=4,
                              locking_duration_coefficient_2=8,
                              maximum_rewarded_periods=4,
                              hours_per_period=1,
                              minimum_locked_periods=2,
                              minimum_allowed_locked=100,
                              maximum_allowed_locked=5 * 10 ** 8,
                              minimum_worker_periods=1)
    return economics


@pytest.fixture()
def token(token_economics, deploy_contract):
    # Create an ERC20 token
    contract, _ = deploy_contract('NuCypherToken', _totalSupplyOfTokens=token_economics.erc20_total_supply)
    return contract


@pytest.mark.nightly
def test_sampling_distribution(testerchain, token, deploy_contract, token_economics):

    #
    # SETUP
    #

    staking_escrow_contract, _ = deploy_contract(
        STAKING_ESCROW_CONTRACT_NAME,
        token.address,
        *token_economics.staking_deployment_parameters,
        _isTestContract=False
    )
    staking_agent = StakingEscrowAgent(registry=None, contract=staking_escrow_contract)

    policy_manager, _ = deploy_contract(
        'PolicyManagerForStakingEscrowMock', token.address, staking_escrow_contract.address
    )
    tx = staking_escrow_contract.functions.setPolicyManager(policy_manager.address).transact()
    testerchain.wait_for_receipt(tx)

    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(hours=1)

    creator = testerchain.etherbase_account

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.approve(staking_escrow_contract.address, 10 ** 9).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    tx = staking_escrow_contract.functions.initialize(10 ** 9).transact({'from': creator})
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
        tx = token.functions.approve(staking_escrow_contract.address, balance).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

        staking_agent.deposit_tokens(amount=balance, lock_periods=10, sender_address=staker, staker_address=staker)
        staking_agent.set_worker(staker_address=staker, worker_address=staker)
        staking_agent.confirm_activity(staker)

    # Wait next period and check all locked tokens
    testerchain.time_travel(hours=1)

    #
    # Test sampling distribution
    #

    ERROR_TOLERANCE = 0.05  # With this tolerance, all sampling ratios should between 5% and 15% (expected is 10%)
    SAMPLES = 1000
    quantity = 3
    counter = Counter()

    sampled, failed = 0, 0
    while sampled < SAMPLES:
        try:
            addresses = set(staking_agent.sample(quantity=quantity, additional_ursulas=1, duration=1))
            addresses.discard(NULL_ADDRESS)
        except staking_agent.NotEnoughStakers:
            failed += 1
            continue
        else:
            sampled += 1
            counter.update(addresses)

    total_times = sum(counter.values())

    expected = amount / all_locked_tokens
    for staker in stakers:
        times = counter[staker]
        sampled_ratio = times / total_times
        abs_error = abs(expected - sampled_ratio)
        assert abs_error < ERROR_TOLERANCE

    # TODO: Test something wrt to % of failed
