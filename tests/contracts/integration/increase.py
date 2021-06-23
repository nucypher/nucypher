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
from collections import Callable

from nucypher.blockchain.eth.agents import StakingEscrowAgent, NucypherTokenAgent, PolicyManagerAgent, ContractAgency
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower

# Experimental max error
from tests.contracts.integration.utils import commit_to_next_period, prepare_staker, MAX_NUNIT_ERROR


def check_rewards_ratios_after_increase(testerchain,
                                        agency,
                                        token_economics,
                                        test_registry,
                                        increase_callable: Callable,
                                        skip_problematic_assertions_after_increase=False):      # set to True to allow values to be printed and failing assertions skipped
    num_test_periods = 20
    min_periods_before_increase = 10

    testerchain.time_travel(hours=1)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    _policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)

    origin = testerchain.etherbase_account
    ursula1 = testerchain.ursula_account(0)  # staker that will stake minimum
    ursula2 = testerchain.ursula_account(1)  # staker that will also stake minimum
    ursula3 = testerchain.ursula_account(2)  # staker that will stake 2x minimum
    ursula3_staking_ratio = 2  # 2x min stake
    ursula4 = testerchain.ursula_account(3)  # staker that will stake minimum but then increase stake to 2x minimum

    origin_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=origin)
    ursula1_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula1)
    ursula2_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula2)
    ursula3_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula3)
    ursula4_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula4)
    ursulas_tpowers = [ursula1_tpower, ursula2_tpower, ursula3_tpower, ursula4_tpower]

    configs = [(ursula1, ursula1_tpower, token_economics.minimum_allowed_locked),  # simple staker staking minimum
               (ursula2, ursula2_tpower, token_economics.minimum_allowed_locked),  # other staker staking minimum
               (ursula3, ursula3_tpower, token_economics.minimum_allowed_locked * ursula3_staking_ratio),  # staker staking 2x minimum
               (ursula4, ursula4_tpower, token_economics.minimum_allowed_locked)   # staker starting with minimum but will increase stake
               ]
    for config in configs:
        prepare_staker(origin_tpower, staking_agent, token_agent, token_economics, config[0], config[1], config[2])

    commit_to_next_period(staking_agent, ursulas_tpowers)
    testerchain.time_travel(periods=1)
    commit_to_next_period(staking_agent, ursulas_tpowers)

    # no staking rewards as yet
    assert staking_agent.calculate_staking_reward(staker_address=ursula1) == 0
    assert staking_agent.calculate_staking_reward(staker_address=ursula2) == 0
    assert staking_agent.calculate_staking_reward(staker_address=ursula3) == 0
    assert staking_agent.calculate_staking_reward(staker_address=ursula4) == 0

    # Get rewards
    ursula1_prior_period_cumulative_rewards = None
    ursula2_prior_period_cumulative_rewards = None
    ursula3_prior_period_cumulative_rewards = None
    ursula4_prior_period_cumulative_rewards = None

    ursula4_period_of_increase = -1

    ursula1_total_rewards_at_increase = None
    ursula2_total_rewards_at_increase = None
    ursula3_total_rewards_at_increase = None
    ursula4_total_rewards_at_increase = None

    for i in range(1, num_test_periods+1):
        testerchain.time_travel(periods=1)
        commit_to_next_period(staking_agent, ursulas_tpowers)

        ursula1_rewards = staking_agent.calculate_staking_reward(staker_address=ursula1)
        ursula2_rewards = staking_agent.calculate_staking_reward(staker_address=ursula2)
        ursula3_rewards = staking_agent.calculate_staking_reward(staker_address=ursula3)
        ursula4_rewards = staking_agent.calculate_staking_reward(staker_address=ursula4)

        if ursula4_period_of_increase == -1:
            # still in phase before ursula4 increases their stake

            # compare cumulative rewards
            assert ursula1_rewards == ursula2_rewards, f"rewards minted during {i} for {i-1}"  # staking the same
            assert ursula4_rewards == ursula1_rewards, f"rewards minted during {i} for {i-1}"  # pre-increase
            assert abs(ursula3_rewards - ursula1_rewards - ursula2_rewards) < MAX_NUNIT_ERROR, \
                f"rewards minted during {i} for {i-1}"  # 2x
        else:
            # increase of stake performed by ursula4

            # per period reward check
            ursula1_reward_for_period = (NU.from_nunits(ursula1_rewards)
                                         - ursula1_prior_period_cumulative_rewards)
            ursula2_reward_for_period = (NU.from_nunits(ursula2_rewards)
                                         - ursula2_prior_period_cumulative_rewards)
            ursula3_reward_for_period = (NU.from_nunits(ursula3_rewards)
                                         - ursula3_prior_period_cumulative_rewards)
            ursula4_reward_for_period = (NU.from_nunits(ursula4_rewards)
                                         - ursula4_prior_period_cumulative_rewards)

            print(f">>> ursula1 reward calculated during period {i} for {i - 1}: {ursula1_reward_for_period}")
            print(f">>> ursula2 reward calculated during period {i} for {i - 1}: {ursula2_reward_for_period}")
            print(f">>> ursula3 reward calculated during period {i} for {i - 1}: {ursula3_reward_for_period}")
            print(f">>> ursula4 reward calculated during period {i} for {i - 1}: {ursula4_reward_for_period}")

            if i == (ursula4_period_of_increase + 1):
                # this is the first period after increase
                assert skip_problematic_assertions_after_increase \
                       or (ursula1_reward_for_period == ursula2_reward_for_period)  # staking the same

                # minted rewards for prior period (when stake was still same size) in which case reward for period should still be equal
                assert skip_problematic_assertions_after_increase \
                       or (ursula4_reward_for_period == ursula1_reward_for_period)
                assert abs(ursula3_reward_for_period.to_tokens()
                           - ursula1_reward_for_period.to_tokens()
                           - ursula2_reward_for_period.to_tokens()) < MAX_NUNIT_ERROR

                ursula1_total_rewards_at_increase = NU.from_nunits(ursula1_rewards)
                ursula2_total_rewards_at_increase = NU.from_nunits(ursula2_rewards)
                ursula3_total_rewards_at_increase = NU.from_nunits(ursula3_rewards)
                ursula4_total_rewards_at_increase = NU.from_nunits(ursula4_rewards)
                print(f">>> ursula1 total rewards when increase occurred {ursula1_total_rewards_at_increase}")
                print(f">>> ursula2 total rewards when increase occurred {ursula2_total_rewards_at_increase}")
                print(f">>> ursula3 total rewards when increase occurred {ursula3_total_rewards_at_increase}")
                print(f">>> ursula4 total rewards when increase occurred {ursula4_total_rewards_at_increase}")
            else:
                # ursula 1 and ursula 2 sill receive same rewards after increase
                assert (ursula2_reward_for_period == ursula1_reward_for_period), f"rewards minted during {i} for {i-1}"

                # ursula3 and ursula4 now staking the same amount after increase so receive same rewards
                assert (ursula3_reward_for_period == ursula4_reward_for_period), f"rewards minted during {i} for {i-1}"

                # ursula4, ursula3 now staking 2x ursula1, ursula2
                assert abs(ursula4_reward_for_period.to_tokens()
                           - ursula1_reward_for_period.to_tokens()
                           - ursula2_reward_for_period.to_tokens()) < MAX_NUNIT_ERROR, \
                    f"per period reward during period {i} for period {i-1}; increase performed in {ursula4_period_of_increase}"

                # now we check total rewards since increase performed by ursula2
                ursula1_total_rewards_since_increase = (NU.from_nunits(ursula1_rewards)
                                                        - ursula1_total_rewards_at_increase)

                ursula2_total_rewards_since_increase = (NU.from_nunits(ursula2_rewards)
                                                        - ursula2_total_rewards_at_increase)

                ursula3_total_rewards_since_increase = (NU.from_nunits(ursula3_rewards)
                                                        - ursula3_total_rewards_at_increase)

                ursula4_total_rewards_since_increase = (NU.from_nunits(ursula4_rewards)
                                                        - ursula4_total_rewards_at_increase)

                print(f">>> ursula1 rewards since increase: {ursula1_total_rewards_since_increase}")
                print(f">>> ursula2 rewards since increase: {ursula2_total_rewards_since_increase}")
                print(f">>> ursula3 rewards since increase: {ursula3_total_rewards_since_increase}")
                print(f">>> ursula4 rewards since increase: {ursula4_total_rewards_since_increase}")

                # total rewards received since increase occurred
                # ursula1 and ursula2 receive the same
                assert ursula1_total_rewards_since_increase == ursula2_total_rewards_since_increase

                # ursula3 should receive same as ursula4 since increase since staking same amount since increase
                assert ursula4_total_rewards_since_increase == ursula3_total_rewards_since_increase

                # ursula4 should receive 2x ursula1 and ursula2 rewards
                assert abs(ursula4_total_rewards_since_increase.to_tokens()
                           - ursula1_total_rewards_since_increase.to_tokens()
                           - ursula2_total_rewards_since_increase.to_tokens()) < MAX_NUNIT_ERROR

        # update cumulative rewards values
        ursula1_prior_period_cumulative_rewards = NU.from_nunits(ursula1_rewards)
        ursula2_prior_period_cumulative_rewards = NU.from_nunits(ursula2_rewards)
        ursula3_prior_period_cumulative_rewards = NU.from_nunits(ursula3_rewards)
        ursula4_prior_period_cumulative_rewards = NU.from_nunits(ursula4_rewards)

        # Perform ursula4 increase of stake at a random period (switch//10) in phase 1
        if (i >= min_periods_before_increase) \
                and ursula4_rewards >= token_economics.minimum_allowed_locked \
                and ursula4_period_of_increase == -1:
            # minimum periods elapsed before attempting increase
            # AND enough rewards received to stake min stake amount
            # AND not already previously increased

            lock_periods = 100 * token_economics.maximum_rewarded_periods  # winddown is off
            amount = token_economics.minimum_allowed_locked
            increase_callable(i, staking_agent, lock_periods, amount, ursula4_tpower)
            ursula4_period_of_increase = i
            ursula4_prior_period_cumulative_rewards -= NU.from_nunits(
                token_economics.minimum_allowed_locked)  # adjust for amount taken out of unlocked rewards

    assert ursula4_period_of_increase != -1, "increase of stake actually occurred"
