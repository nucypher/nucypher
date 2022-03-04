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


from typing import TypeVar, NewType, NamedTuple, Union

from eth_typing.evm import ChecksumAddress
from web3.types import Wei, TxReceipt

ERC20UNits = NewType("ERC20UNits", int)
NuNits = NewType("NuNits", ERC20UNits)
TuNits = NewType("TuNits", ERC20UNits)

Work = NewType("Work", int)
Agent = TypeVar('Agent', bound='EthereumContractAgent')
Period = NewType('Period', int)
PeriodDelta = NewType('PeriodDelta', int)
ContractReturnValue = TypeVar('ContractReturnValue', bound=Union[TxReceipt, Wei, int, str, bool])


class StakingProviderInfo(NamedTuple):
    operator: ChecksumAddress
    operator_confirmed: bool
    operator_start_timestamp: int


class PolicyInfo(NamedTuple):
    disabled: bool
    sponsor: ChecksumAddress
    owner: ChecksumAddress
    fee_rate: Wei
    start_timestamp: int
    end_timestamp: int

    # reserved but unused fields in the corresponding Solidity structure below
    # reserved_slot_1
    # reserved_slot_2
    # reserved_slot_3
    # reserved_slot_4
    # reserved_slot_5


class ArrangementInfo(NamedTuple):
    node: ChecksumAddress
    downtime_index: int
    last_refunded_period: int
