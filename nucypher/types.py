


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
