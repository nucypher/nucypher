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


# Conditions
class _AccessControlCondition(TypedDict):
    name: NotRequired[str]
    conditionType: str


class BaseExecConditionDict(_AccessControlCondition):
    returnValueTest: ReturnValueTestDict


class RPCConditionDict(BaseExecConditionDict):
    chain: int
    method: str
    parameters: NotRequired[List[Any]]


class TimeConditionDict(RPCConditionDict):
    pass


class ContractConditionDict(RPCConditionDict):
    contractAddress: str
    standardContractType: NotRequired[str]
    functionAbi: NotRequired[ABIFunction]


class JsonApiConditionDict(BaseExecConditionDict):
    endpoint: str
    query: NotRequired[str]
    parameters: NotRequired[Dict]

#
# CompoundCondition represents:
# {
#     "operator": ["and" | "or" | "not"]
#     "operands": List[AccessControlCondition]
# }
#
class CompoundConditionDict(_AccessControlCondition):
    operator: Literal["and", "or", "not"]
    operands: List["ConditionDict"]


#
# ConditionVariable represents:
# {
#     varName: str
#     condition: AccessControlCondition
# }
#
class ConditionVariableDict(TypedDict):
    varName: str
    condition: "ConditionDict"


#
# SequentialCondition represents:
# {
#     "conditionVariables": List[ConditionVariable]
# }
#
class SequentialConditionDict(_AccessControlCondition):
    conditionVariables = List[ConditionVariableDict]


#
# ConditionDict is a dictionary of:
# - TimeCondition
# - RPCCondition
# - ContractCondition
# - CompoundConditionDict
# - JsonApiConditionDict
# - SequentialConditionDict
ConditionDict = Union[
    TimeConditionDict,
    RPCConditionDict,
    ContractConditionDict,
    CompoundConditionDict,
    JsonApiConditionDict,
    SequentialConditionDict,
]


#
# Lingo is:
# - version
# - condition
#     - ConditionDict
class Lingo(TypedDict):
    version: str
    condition: ConditionDict
