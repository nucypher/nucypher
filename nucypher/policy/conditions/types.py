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

OperatorLiteral = Literal["==", "!=", ">", "<", ">=", "<="]


# Return Value Test
class ReturnValueTestDict(TypedDict):
    comparator: OperatorLiteral
    value: Any
    key: NotRequired[Union[str, int]]


class _ReencryptionConditionDict(TypedDict):
    name: NotRequired[str]


class TimeConditionDict(_ReencryptionConditionDict):
    method: Literal["timelock"]
    returnValueTest: ReturnValueTestDict


class RPCConditionDict(_ReencryptionConditionDict):
    chain: int
    method: str
    parameters: NotRequired[List[Any]]
    returnValueTest: ReturnValueTestDict


class ContractConditionDict(RPCConditionDict):
    contractAddress: str
    standardContractType: NotRequired[str]
    functionAbi: NotRequired[ABIFunction]


ConditionDict = Union[TimeConditionDict, RPCConditionDict, ContractConditionDict]

#
# LingoListEntry is:
# - Condition
# - Operator
#
LingoListEntry = Union[OperatorDict, ConditionDict]

#
# LingoList contains a list of LingoEntries
LingoList = List[LingoListEntry]
