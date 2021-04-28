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


from decimal import Decimal, localcontext
from math import log
from typing import Tuple

from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NucypherTokenAgent,
    StakingEscrowAgent,
    WorkLockAgent
)
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import NU

LOG2 = Decimal(log(2))
ONE_YEAR_IN_HOURS = 365 * 24


class BaseEconomics:
    """
    A representation of a contract deployment set's constructor parameters, and the calculations
    used to generate those values from high-level human-understandable parameters.

    Formula for staking in one period for the second phase:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / d / k2

    d - Coefficient which modifies the rate at which the maximum issuance decays
    k1 - Numerator of the locking duration coefficient
    k2 - Denominator of the locking duration coefficient

    if allLockedPeriods > maximum_rewarded_periods then allLockedPeriods = maximum_rewarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / d

    """

    # Token Denomination
    __token_decimals = 18
    nunits_per_token = 10 ** __token_decimals  # Smallest unit designation

    # Period Definition
    _default_hours_per_period = 24 * 7
    _default_genesis_hours_per_period = 24

    # Time Constraints
    _default_minimum_worker_periods = 2
    _default_minimum_locked_periods = 4  # 28 days

    # Value Constraints
    _default_minimum_allowed_locked = NU(15_000, 'NU').to_nunits()
    _default_maximum_allowed_locked = NU(30_000_000, 'NU').to_nunits()

    # Slashing parameters
    HASH_ALGORITHM_KECCAK256 = 0
    HASH_ALGORITHM_SHA256 = 1
    HASH_ALGORITHM_RIPEMD160 = 2

    # Adjudicator
    _default_hash_algorithm = HASH_ALGORITHM_SHA256
    _default_base_penalty = 2
    _default_penalty_history_coefficient = 0
    _default_percentage_penalty_coefficient = 100000  # 0.001%
    _default_reward_coefficient = 2

    # Worklock
    from maya import MayaDT
    from web3 import Web3
    _default_worklock_supply: int = NU(225_000_000, 'NU').to_nunits()
    _default_bidding_start_date: int = MayaDT.from_iso8601('2020-09-01T00:00:00.0Z').epoch
    _default_bidding_end_date: int = MayaDT.from_iso8601('2020-09-28T23:59:59.0Z').epoch
    _default_cancellation_end_date: int = MayaDT.from_iso8601('2020-09-30T23:59:59.0Z').epoch
    _default_worklock_boosting_refund_rate: int = 800
    _default_worklock_commitment_duration: int = 180
    _default_worklock_min_allowed_bid: int = Web3.toWei(5, "ether")

    def __init__(self,

                 # StakingEscrow
                 initial_supply: int,
                 total_supply: int,
                 issuance_decay_coefficient: int,
                 lock_duration_coefficient_1: int,
                 lock_duration_coefficient_2: int,
                 maximum_rewarded_periods: int,
                 first_phase_supply: int,
                 first_phase_max_issuance: int,
                 genesis_hours_per_period: int = _default_genesis_hours_per_period,
                 hours_per_period: int = _default_hours_per_period,
                 minimum_locked_periods: int = _default_minimum_locked_periods,
                 minimum_allowed_locked: int = _default_minimum_allowed_locked,
                 maximum_allowed_locked: int = _default_maximum_allowed_locked,
                 minimum_worker_periods: int = _default_minimum_worker_periods,

                 # Adjudicator
                 hash_algorithm: int = _default_hash_algorithm,
                 base_penalty: int = _default_base_penalty,
                 penalty_history_coefficient: int = _default_penalty_history_coefficient,
                 percentage_penalty_coefficient: int = _default_percentage_penalty_coefficient,
                 reward_coefficient: int = _default_reward_coefficient,

                 # WorkLock
                 worklock_supply: int = _default_worklock_supply,
                 bidding_start_date: int = _default_bidding_start_date,
                 bidding_end_date: int = _default_bidding_end_date,
                 cancellation_end_date: int = _default_cancellation_end_date,
                 worklock_boosting_refund_rate: int = _default_worklock_boosting_refund_rate,
                 worklock_commitment_duration: int = _default_worklock_commitment_duration,
                 worklock_min_allowed_bid: int = _default_worklock_min_allowed_bid):

        """
        :param initial_supply: Number of tokens in circulating supply at t=0
        :param first_phase_supply: Number of tokens in circulating supply at phase switch (variable t)
        :param total_supply: Tokens at t=8
        :param first_phase_max_issuance: (Imax) Maximum number of new tokens minted per period during Phase 1.
        See Equation 7 in Staking Protocol & Economics paper.
        :param issuance_decay_coefficient: (d) Coefficient which modifies the rate at which the maximum issuance decays,
        only applicable to Phase 2. d = 365 * half-life / LOG2 where default half-life = 2.
        See Equation 10 in Staking Protocol & Economics paper
        :param lock_duration_coefficient_1: (k1) Numerator of the coefficient which modifies the extent
        to which a stake's lock duration affects the subsidy it receives. Affects stakers differently.
        Applicable to Phase 1 and Phase 2. k1 = k2 * small_stake_multiplier where default small_stake_multiplier = 0.5.
        See Equation 8 in Staking Protocol & Economics paper.
        :param lock_duration_coefficient_2: (k2) Denominator of the coefficient which modifies the extent
        to which a stake's lock duration affects the subsidy it receives. Affects stakers differently.
        Applicable to Phase 1 and Phase 2. k2 = maximum_rewarded_periods / (1 - small_stake_multiplier)
        where default maximum_rewarded_periods = 365 and default small_stake_multiplier = 0.5.
        See Equation 8 in Staking Protocol & Economics paper.
        :param maximum_rewarded_periods: (kmax) Number of periods beyond which a stake's lock duration
        no longer increases the subsidy it receives. kmax = reward_saturation * 365 where default reward_saturation = 1.
        See Equation 8 in Staking Protocol & Economics paper.
        :param genesis_hours_per_period: Hours in single period at genesis
        :param hours_per_period: Hours in single period
        :param minimum_locked_periods: Min amount of periods during which tokens can be locked
        :param minimum_allowed_locked: Min amount of tokens that can be locked
        :param maximum_allowed_locked: Max amount of tokens that can be locked
        :param minimum_worker_periods: Min amount of periods while a worker can't be changed

        :param hash_algorithm: Hashing algorithm
        :param base_penalty: Base for the penalty calculation
        :param penalty_history_coefficient: Coefficient for calculating the penalty depending on the history
        :param percentage_penalty_coefficient: Coefficient for calculating the percentage penalty
        :param reward_coefficient: Coefficient for calculating the reward
        """

        #
        # WorkLock
        #

        self.bidding_start_date = bidding_start_date
        self.bidding_end_date = bidding_end_date
        self.cancellation_end_date = cancellation_end_date
        self.worklock_supply = worklock_supply
        self.worklock_boosting_refund_rate = worklock_boosting_refund_rate
        self.worklock_commitment_duration = worklock_commitment_duration
        self.worklock_min_allowed_bid = worklock_min_allowed_bid

        #
        # NucypherToken & Staking Escrow
        #

        self.initial_supply = initial_supply
        # Remaining / Reward Supply - Escrow Parameter
        self.reward_supply = total_supply - initial_supply
        self.total_supply = total_supply
        self.first_phase_supply = first_phase_supply
        self.first_phase_total_supply = initial_supply + first_phase_supply
        self.first_phase_max_issuance = first_phase_max_issuance
        self.issuance_decay_coefficient = issuance_decay_coefficient
        self.lock_duration_coefficient_1 = lock_duration_coefficient_1
        self.lock_duration_coefficient_2 = lock_duration_coefficient_2
        self.maximum_rewarded_periods = maximum_rewarded_periods
        self.genesis_hours_per_period = genesis_hours_per_period
        self.hours_per_period = hours_per_period
        self.minimum_locked_periods = minimum_locked_periods
        self.minimum_allowed_locked = minimum_allowed_locked
        self.maximum_allowed_locked = maximum_allowed_locked
        self.minimum_worker_periods = minimum_worker_periods
        self.genesis_seconds_per_period = genesis_hours_per_period * 60 * 60  # Genesis seconds in a single period
        self.seconds_per_period = hours_per_period * 60 * 60  # Seconds in a single period
        self.days_per_period = hours_per_period // 24  # Days in a single period

        #
        # Adjudicator
        #

        self.hash_algorithm = hash_algorithm
        self.base_penalty = base_penalty
        self.penalty_history_coefficient = penalty_history_coefficient
        self.percentage_penalty_coefficient = percentage_penalty_coefficient
        self.reward_coefficient = reward_coefficient

    @property
    def erc20_initial_supply(self) -> int:
        return int(self.initial_supply)

    @property
    def erc20_reward_supply(self) -> int:
        return int(self.reward_supply)

    @property
    def erc20_total_supply(self) -> int:
        return int(self.total_supply)

    @property
    def staking_deployment_parameters(self) -> Tuple[int, ...]:
        """Cast coefficient attributes to uint256 compatible type for solidity+EVM"""
        deploy_parameters = (

            # Period
            self.genesis_hours_per_period,  # Hours in single period at genesis
            self.hours_per_period,  # Hours in single period

            # Coefficients
            self.issuance_decay_coefficient,  # Coefficient which modifies the rate at which the maximum issuance decays (d)
            self.lock_duration_coefficient_1,  # Numerator of the locking duration coefficient (k1)
            self.lock_duration_coefficient_2,  # Denominator of the locking duration coefficient (k2)
            self.maximum_rewarded_periods,  # Max periods that will be additionally rewarded (awarded_periods)
            self.first_phase_total_supply,  # Total supply for the first phase
            self.first_phase_max_issuance,  # Max possible reward for one period for all stakers in the first phase

            # Constraints
            self.minimum_locked_periods,  # Min amount of periods during which tokens can be locked
            self.minimum_allowed_locked,  # Min amount of tokens that can be locked
            self.maximum_allowed_locked,  # Max amount of tokens that can be locked
            self.minimum_worker_periods             # Min amount of periods while a worker can't be changed
        )
        return tuple(map(int, deploy_parameters))

    @property
    def slashing_deployment_parameters(self) -> Tuple[int, ...]:
        """Cast coefficient attributes to uint256 compatible type for solidity+EVM"""
        deployment_parameters = [
            self.hash_algorithm,
            self.base_penalty,
            self.penalty_history_coefficient,
            self.percentage_penalty_coefficient,
            self.reward_coefficient
        ]
        return tuple(map(int, deployment_parameters))

    @property
    def worklock_deployment_parameters(self):
        """
        0 token - Token contract
        1 escrow -  Staking Escrow contract
        ...
        2 startBidDate - Timestamp when bidding starts
        3 endBidDate - Timestamp when bidding will end
        4 endCancellationDate - Timestamp when cancellation window will end
        5 boostingRefund - Coefficient to boost refund ETH
        6 stakingPeriods - Duration of tokens locking
        7 minAllowedBid - Minimum allowed ETH amount for bidding
        """
        deployment_parameters = [self.bidding_start_date,
                                 self.bidding_end_date,
                                 self.cancellation_end_date,
                                 self.worklock_boosting_refund_rate,
                                 self.worklock_commitment_duration,
                                 self.worklock_min_allowed_bid]
        return tuple(map(int, deployment_parameters))

    @property
    def bidding_duration(self) -> int:
        """Returns the total bidding window duration in seconds."""
        return self.bidding_end_date - self.bidding_start_date

    @property
    def cancellation_window_duration(self) -> int:
        """Returns the total cancellation window duration in seconds."""
        return self.cancellation_end_date - self.bidding_end_date


class StandardTokenEconomics(BaseEconomics):
    """

    Formula for staking in one period for the second phase:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / d / k2

    d - Coefficient which modifies the rate at which the maximum issuance decays
    k1 - Numerator of the locking duration coefficient
    k2 - Denominator of the locking duration coefficient

    if allLockedPeriods > maximum_rewarded_periods then allLockedPeriods = maximum_rewarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / d / k2

    ...but also...

    kappa = small_stake_multiplier + (1 - small_stake_multiplier) * min(T, T1) / T1
    where allLockedPeriods == min(T, T1)

    Academic Reference:

    NuCypher: Mining & Staking Economics - Michael Egorov, MacLane Wilkison, NuCypher
    <https://github.com/nucypher/mining-paper/blob/master/mining-paper.pdf>

    """

    # Decimal
    _precision = 28

    # Supply
    __default_initial_supply = NU(int(1_000_000_000), 'NU').to_nunits()
    __default_first_phase_supply = NU(int(1_829_579_800), 'NU').to_nunits()
    __default_first_phase_duration = 5  # years

    __default_decay_half_life = 2    # years
    __default_reward_saturation = 1  # years
    __default_small_stake_multiplier = Decimal(0.5)

    def __init__(self,
                 initial_supply: int = __default_initial_supply,
                 first_phase_supply: int = __default_first_phase_supply,
                 first_phase_duration: int = __default_first_phase_duration,
                 decay_half_life: int = __default_decay_half_life,
                 reward_saturation: int = __default_reward_saturation,
                 small_stake_multiplier: Decimal = __default_small_stake_multiplier,
                 hours_per_period: int = BaseEconomics._default_hours_per_period,
                 **kwargs):
        """
        :param initial_supply: Number of tokens in circulating supply at t=0
        :param first_phase_supply: Number of tokens in circulating supply at phase switch (variable t)
        :param first_phase_duration: Minimum duration of the first phase
        :param decay_half_life: Time for issuance to halve in years (in second phase only)
        :param reward_saturation: "saturation" time - if staking is longer than T_sat, the reward doesn't get any higher
        :param small_stake_multiplier: Fraction of maximum reward paid to those who are about to unlock tokens
        """

        #
        # Calculated
        #

        with localcontext() as ctx:
            ctx.prec = self._precision

            one_year_in_periods = Decimal(ONE_YEAR_IN_HOURS / hours_per_period)

            initial_supply = Decimal(initial_supply)

            first_phase_supply = Decimal(first_phase_supply)

            first_phase_max_issuance = first_phase_supply / first_phase_duration / one_year_in_periods

            # ERC20 Token parameter (See Equation 4 in Mining paper)
            total_supply = initial_supply             \
                           + first_phase_supply       \
                           + first_phase_max_issuance \
                           * one_year_in_periods      \
                           * decay_half_life          \
                           / LOG2

            # Awarded periods- Escrow parameter
            maximum_rewarded_periods = reward_saturation * one_year_in_periods

            # k2 - Escrow parameter
            lock_duration_coefficient_2 = maximum_rewarded_periods / (1 - small_stake_multiplier)

            # k1 - Escrow parameter
            lock_duration_coefficient_1 = lock_duration_coefficient_2 * small_stake_multiplier

            # d - Escrow parameter
            issuance_decay_coefficient = one_year_in_periods * decay_half_life / LOG2


        #
        # Injected
        #

        self.token_halving = decay_half_life
        self.token_saturation = reward_saturation
        self.small_stake_multiplier = small_stake_multiplier

        super().__init__(initial_supply=initial_supply,
                         first_phase_supply=first_phase_supply,
                         total_supply=total_supply,
                         first_phase_max_issuance=first_phase_max_issuance,
                         issuance_decay_coefficient=issuance_decay_coefficient,
                         lock_duration_coefficient_1=lock_duration_coefficient_1,
                         lock_duration_coefficient_2=lock_duration_coefficient_2,
                         maximum_rewarded_periods=int(maximum_rewarded_periods),
                         hours_per_period=hours_per_period,
                         **kwargs)

    def first_phase_final_period(self) -> int:
        """
        Returns final period for first phase,
        assuming that all stakers locked tokens for more than 365 days.
        """
        S_p1 = self.first_phase_supply
        I_s_per_period = self.first_phase_max_issuance  # per period
        phase_switch_in_periods = S_p1 // I_s_per_period
        return int(phase_switch_in_periods)

    def token_supply_at_period(self, period: int) -> int:
        """
        Returns predicted total supply at specified period,
        assuming that all stakers locked tokens for more than 365 days.
        """
        if period < 0:
            raise ValueError("Period must be a positive integer")

        with localcontext() as ctx:
            ctx.prec = self._precision

            t = Decimal(period)
            S_0 = self.erc20_initial_supply
            phase_switch_in_periods = self.first_phase_final_period()
            I_s_per_period = self.first_phase_max_issuance  # per period

            if t <= phase_switch_in_periods:
                S_t = S_0 + t * I_s_per_period
            else:
                one_year_in_periods = Decimal(ONE_YEAR_IN_HOURS / self.hours_per_period)
                S_p1 = self.first_phase_max_issuance * phase_switch_in_periods
                T_half = self.token_halving  # in years
                T_half_in_periods = T_half * one_year_in_periods
                t = t - phase_switch_in_periods

                S_t = S_0 + S_p1 + I_s_per_period * T_half_in_periods * (1 - 2 ** (-t / T_half_in_periods)) / LOG2
            return int(S_t)

    def cumulative_rewards_at_period(self, period: int) -> int:
        return self.token_supply_at_period(period) - self.erc20_initial_supply

    def rewards_during_period(self, period: int) -> int:
        return self.token_supply_at_period(period) - self.token_supply_at_period(period-1)


class EconomicsFactory:
    # TODO: Enforce singleton

    __economics = dict()

    @classmethod
    def get_economics(cls, registry: BaseContractRegistry) -> BaseEconomics:
        registry_id = registry.id
        try:
            return cls.__economics[registry_id]
        except KeyError:
            economics = EconomicsFactory.retrieve_from_blockchain(registry=registry)
            cls.__economics[registry_id] = economics
            return economics

    @staticmethod
    def retrieve_from_blockchain(registry: BaseContractRegistry) -> BaseEconomics:

        # Agents
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
        adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=registry)

        worklock_deployed = True
        try:
            worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)
        except registry.UnknownContract:
            worklock_deployed = False

        # Token
        total_supply = token_agent.contract.functions.totalSupply().call()
        reward_supply = staking_agent.contract.functions.getReservedReward().call()
        # Not the "real" initial_supply value because used current reward instead of initial reward
        initial_supply = total_supply - reward_supply

        # Staking Escrow
        staking_parameters = list(staking_agent.staking_parameters())
        genesis_seconds_per_period = staking_parameters.pop(0)
        seconds_per_period = staking_parameters.pop(0)
        staking_parameters.insert(6, genesis_seconds_per_period // 60 // 60)  # genesis_hours_per_period
        staking_parameters.insert(7, seconds_per_period // 60 // 60)  # hours_per_period
        minting_coefficient = staking_parameters[0]
        lock_duration_coefficient_2 = staking_parameters[2]
        first_phase_total_supply = staking_parameters[4]
        first_phase_supply = first_phase_total_supply - initial_supply
        staking_parameters[4] = first_phase_supply
        staking_parameters[0] = minting_coefficient // lock_duration_coefficient_2  # issuance_decay_coefficient

        # Adjudicator
        slashing_parameters = adjudicator_agent.slashing_parameters()

        # Worklock
        if worklock_deployed:
            worklock_parameters = worklock_agent.worklock_parameters()
        else:
            worklock_parameters = list()

        # Aggregate (order-sensitive)
        economics_parameters = (initial_supply,
                                total_supply,
                                *staking_parameters,
                                *slashing_parameters,
                                *worklock_parameters)

        economics = BaseEconomics(*economics_parameters)
        return economics
