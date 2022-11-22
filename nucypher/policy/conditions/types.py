import sys

if sys.version_info >= (3, 8):
    from typing import Literal, TypedDict
else:
    from typing_extensions import Literal, TypedDict

from typing import Any, Dict, List, Type, Union

from web3.types import ABIFunction

#########
# Context
#########
ContextDict = Dict[str, Any]


################
# ConditionLingo
################

#
# OperatorDict represents:
# - {"operator": "and" | "or"}
class OperatorDict(TypedDict):
    operator: Literal["and", "or"]


#
# ConditionDict is a dictionary of:
# - TimeCondition
# - RPCCondition
# - ContractCondition

# Return Value Test
class ReturnValueTestDict(TypedDict, total=False):
    comparator: str
    value: Any
    key: Union[str, int]


class _ReencryptionConditionDict(TypedDict, total=False):
    name: str


class TimeConditionDict(_ReencryptionConditionDict, total=False):
    method: Literal["timelock"]
    returnValueTest: ReturnValueTestDict


class RPCConditionDict(_ReencryptionConditionDict, total=False):
    chain: int
    method: str
    parameters: List[Any]
    returnValueTest: ReturnValueTestDict


class ContractConditionDict(RPCConditionDict, total=False):
    standardContractType: str
    contractAddress: str
    functionAbi: ABIFunction


ConditionDict = Union[TimeConditionDict, RPCConditionDict, ContractConditionDict]

#
# LingoEntry is:
# - Condition
# - Operator
#
LingoListEntry = Union[OperatorDict, ConditionDict]

#
# LingoList contains a list of LingoEntries
LingoList = List[LingoListEntry]


#
# Object Types
#
LingoEntryObjectType = Union[Type["Operator"], Type["ReencryptionCondition"]]
LingoEntryObject = Union["Operator", "ReencryptionCondition"]
