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


from typing import TypeVar, NewType, Tuple, NamedTuple, Union

from eth_typing.evm import ChecksumAddress
from web3.types import Wei, Timestamp, TxReceipt

NuNits = NewType("NuNits", int)
Work = NewType("Work", int)
Agent = TypeVar('Agent', bound='EthereumContractAgent')
Period = NewType('Period', int)
PeriodDelta = NewType('PeriodDelta', int)
ContractReturnValue = TypeVar('ContractReturnValue', bound=Union[TxReceipt, Wei, int, str, bool])


class WorklockParameters(Tuple):
    token_supply: NuNits
    start_bid_date: Timestamp
    end_bid_date: Timestamp
    end_cancellation_date: Timestamp
    boosting_refund: int
    staking_periods: int
    min_allowed_bid: Wei


class StakingEscrowParameters(Tuple):
    seconds_per_period: int
    minting_coefficient: int
    lock_duration_coefficient_1: int
    lock_duration_coefficient_2: int
    maximum_rewarded_periods: int
    first_phase_total_supply: NuNits
    first_phase_max_issuance: NuNits
    min_locked_periods: PeriodDelta
    min_allowable_locked_tokens: NuNits
    max_allowable_locked_tokens: NuNits
    min_worker_periods: PeriodDelta


class SubStakeInfo(NamedTuple):
    first_period: Period
    last_period: Period
    locked_value: NuNits


class RawSubStakeInfo(NamedTuple):
    first_period: Period
    last_period: Period
    unlocking_duration: int
    locked_value: NuNits


class Downtime(NamedTuple):
    start_period: Period
    end_period: Period


class StakerFlags(NamedTuple):
    wind_down_flag: bool
    restake_flag: bool
    measure_work_flag: bool
    snapshot_flag: bool
    migration_flag: bool


class StakerInfo(NamedTuple):
    value: NuNits
    current_committed_period: Period
    next_committed_period: Period
    last_committed_period: Period
    lock_restake_until_period: Period
    completed_work: NuNits
    worker_start_period: Period
    worker: ChecksumAddress
    flags: bytes
    # downtime: Tuple[Downtime, ...]
    # substake_info: Tuple[RawSubStakeInfo, ...]
    # history: Tuple[NuNits, ...]
