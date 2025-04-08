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
    authorizationToken: NotRequired[str]


class JsonRpcConditionDict(BaseExecConditionDict):
    endpoint: str
    method: str
    params: NotRequired[Any]
    query: NotRequired[str]
    authorizationToken: NotRequired[str]


class JWTConditionDict(_AccessControlCondition):
    jwtToken: str
    publicKey: str  # TODO: See #3572 for a discussion about deprecating this in favour of the expected issuer
    expectedIssuer: NotRequired[str]


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
# IfThenElseCondition represents:
# {
#     "ifCondition": AccessControlCondition
#     "thenCondition": AccessControlCondition
#     "elseCondition": [AccessControlCondition | bool]
# }
class IfThenElseConditionDict(_AccessControlCondition):
    ifCondition: "ConditionDict"
    thenCondition: "ConditionDict"
    elseCondition: Union["ConditionDict", bool]


#
# ConditionDict is a dictionary of:
# - TimeCondition
# - RPCCondition
# - ContractCondition
# - CompoundCondition
# - JsonApiCondition
# - JsonRpcCondition
# - JWTCondition
# - SequentialCondition
# - IfThenElseCondition
ConditionDict = Union[
    TimeConditionDict,
    RPCConditionDict,
    ContractConditionDict,
    CompoundConditionDict,
    JsonApiConditionDict,
    JsonRpcConditionDict,
    JWTConditionDict,
    SequentialConditionDict,
    IfThenElseConditionDict,
]


#
# Lingo is:
# - version
# - condition
#     - ConditionDict
class Lingo(TypedDict):
    version: str
    condition: ConditionDict
