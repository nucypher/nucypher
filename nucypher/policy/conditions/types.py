import sys

if sys.version_info >= (3, 11):
    # Necessary because of `NotRequired` import - https://peps.python.org/pep-0655/
    from typing import Literal, NotRequired, TypedDict
elif sys.version_info >= (3, 8):
    from typing import Literal

    from typing_extensions import NotRequired, TypedDict
else:
    from typing_extensions import Literal, NotRequired, TypedDict

from typing import Any, Dict, List, Union

from web3.types import ABIFunction

#########
# Context
#########
ContextDict = Dict[str, Any]


################
# ConditionLingo
################

ComparatorLiteral = Literal["==", "!=", ">", "<", ">=", "<="]


# Return Value Test
class ReturnValueTestDict(TypedDict):
    comparator: ComparatorLiteral
    value: Any
    key: NotRequired[Union[str, int]]


class _AccessControlCondition(TypedDict):
    name: NotRequired[str]


class RPCConditionDict(_AccessControlCondition):
    conditionType: str
    chain: int
    method: str
    parameters: NotRequired[List[Any]]
    returnValueTest: ReturnValueTestDict


class TimeConditionDict(RPCConditionDict):
    pass


class ContractConditionDict(RPCConditionDict):
    contractAddress: str
    standardContractType: NotRequired[str]
    functionAbi: NotRequired[ABIFunction]


#
# CompoundCondition represents:
# {
#     "operator": ["and" | "or"]
#     "operands": List[AccessControlCondition | CompoundCondition]
#
#
class CompoundConditionDict(TypedDict):
    conditionType: str
    operator: Literal["and", "or"]
    operands: List["Lingo"]


#
# ConditionDict is a dictionary of:
# - TimeCondition
# - RPCCondition
# - ContractCondition
# - CompoundConditionDict
ConditionDict = Union[
    TimeConditionDict, RPCConditionDict, ContractConditionDict, CompoundConditionDict
]


#
# Lingo is:
# - version
# - condition
#     - ConditionDict
class Lingo(TypedDict):
    version: str
    condition: ConditionDict
