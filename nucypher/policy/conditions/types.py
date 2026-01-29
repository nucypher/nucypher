import sys

# Our python support is [3.10 - 3.13]
if sys.version_info >= (3, 11):
    # Necessary because of `NotRequired` import - https://peps.python.org/pep-0655/
    from typing import Literal, NotRequired, TypedDict
else:
    # v3.10
    from typing import Literal

    from typing_extensions import NotRequired, TypedDict

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


# VariableOperation
class VariableOperation(TypedDict):
    operation: str
    value: NotRequired[Any]


# Return Value Test
class ReturnValueTestDict(TypedDict):
    comparator: ComparatorLiteral
    value: Any
    index: NotRequired[int]
    operations: NotRequired[List[VariableOperation]]


# Conditions
class _Condition(TypedDict):
    name: NotRequired[str]
    conditionType: str


class BaseExecConditionDict(_Condition):
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


class JsonConditionDict(BaseExecConditionDict):
    data: str  # Must be a context variable (e.g., ":previousResult")
    query: NotRequired[str]


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


class JWTConditionDict(_Condition):
    jwtToken: str
    publicKey: str  # TODO: See #3572 for a discussion about deprecating this in favour of the expected issuer
    expectedIssuer: NotRequired[str]


#
# ContextVariableCondition represents:
# {
#     "conditionType": "context-var",
#     "contextVariable": str
#     "returnValueTest": <>
# }
#
class ContextVariableConditionDict(BaseExecConditionDict):
    contextVariable: str


#
# CompoundCondition represents:
# {
#     "operator": ["and" | "or" | "not" | "at-least"]
#     "operands": List[Condition]
#     "threshold": int (Optional)
# }
#
class CompoundConditionDict(_Condition):
    operator: Literal["and", "or", "not", "at-least"]
    operands: List["ConditionDict"]
    threshold: NotRequired[int]


#
# ConditionVariable represents:
# {
#     varName: str
#     condition: Condition
# }
#
class ConditionVariableDict(TypedDict):
    varName: str
    condition: "ConditionDict"
    operations: NotRequired[List[VariableOperation]]


#
# SequentialCondition represents:
# {
#     "conditionVariables": List[ConditionVariable]
# }
#
class SequentialConditionDict(_Condition):
    conditionVariables = List[ConditionVariableDict]


#
# IfThenElseCondition represents:
# {
#     "ifCondition": Condition
#     "thenCondition": Condition
#     "elseCondition": [Condition | bool]
# }
class IfThenElseConditionDict(_Condition):
    ifCondition: "ConditionDict"
    thenCondition: "ConditionDict"
    elseCondition: Union["ConditionDict", bool]


#
# ECDSACondition represents:
# {
#     "message": [bytes | str]
#     "signature": str
#     "verifyingKey": str
#     "curve": str
# }
class ECDSAConditionDict(_Condition):
    message: Union[bytes, str]
    signature: str
    verifyingKey: str
    curve: str


# _SigningObjectCondition abstract class represents:
# {
#     "signingObjectContextVar": ":signingConditionObject"
# }
class _SigningObjectCondition(_Condition):
    signingObjectContextVar: str


# _BaseSigningObjectAttributeCondition abstract class represents:
# {
#     "signingObjectContextVar": ":signingConditionObject"
#     "attributeName": str
# }
class _BaseSigningObjectAttributeCondition(_SigningObjectCondition):
    attributeName: str


# SigningObjectAttributeCondition represents:
# {
#     "attributeName": str
#     "signingObjectContextVar": ":signingConditionObject"
#     "returnValueTest: <>
# }
class SigningObjectAttributeCondition(_BaseSigningObjectAttributeCondition):
    returnValueTest: ReturnValueTestDict


# AbiParameterValidation represents:
# {
#     "parameterIndex": int
#     "subIndices": [int]  # Sequential indices for navigating nested structures
#     "returnValueTest: <>
#     "nestedAbiValidation: <>
# }
class AbiParameterValidation(TypedDict):
    parameterIndex: int
    subIndices: NotRequired[List[int]]
    # either returnValueTest or nestedAbiValidation
    returnValueTest: NotRequired[ReturnValueTestDict]
    nestedAbiValidation: NotRequired["AbiCallValidation"]


# AbiCallValidation
# {
#    "allowedAbiCalls": {
#        <call>: ["AbiParameterValidation"]
#    }
# }
class AbiCallValidation(TypedDict):
    allowedAbiCalls = Dict[str, List[AbiParameterValidation]]


# SigningObjectAbiAttributeCondition represents:
# {
#     "attributeName": str
#     "signingObjectContextVar": ":signingConditionObject"
#     "abiValidation": <abi_call_validation>
# }
class SigningObjectAbiAttributeCondition(_BaseSigningObjectAttributeCondition):
    abiValidation: AbiCallValidation


#
# ConditionDict is a dictionary of:
# - TimeCondition
# - RPCCondition
# - ContractCondition
# - CompoundCondition
# - JsonCondition
# - JsonApiCondition
# - JsonRpcCondition
# - JWTCondition
# - SequentialCondition
# - IfThenElseCondition
# - ECDSACondition
# - SigningObjectAttributeCondition
# - SigningObjectAbiAttributeCondition
# - ContextVariableConditionDict
ConditionDict = Union[
    TimeConditionDict,
    RPCConditionDict,
    ContractConditionDict,
    CompoundConditionDict,
    JsonConditionDict,
    JsonApiConditionDict,
    JsonRpcConditionDict,
    JWTConditionDict,
    SequentialConditionDict,
    IfThenElseConditionDict,
    ECDSAConditionDict,
    SigningObjectAttributeCondition,
    SigningObjectAbiAttributeCondition,
    ContextVariableConditionDict,
]


#
# Lingo is:
# - version
# - condition
#     - ConditionDict
class Lingo(TypedDict):
    version: str
    condition: ConditionDict
