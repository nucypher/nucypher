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
# AddressAllowlistCondition represents:
# {
#     "conditionType": "address-allowlist",
#     "addresses": List[str] (Ethereum addresses)
#     "userAddress": str (Ethereum address)
# }
#
class AddressAllowlistConditionDict(_AccessControlCondition):
    addresses: List[str]
    userAddress: str


#
# CompoundCondition represents:
# {
#     "operator": ["and" | "or" | "not"]
#     "operands": List[Condition]
# }
#
class CompoundConditionDict(_Condition):
    operator: Literal["and", "or", "not"]
    operands: List["ConditionDict"]


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
# }
class ECDSAConditionDict(_Condition):
    message: Union[bytes, str]
    signature: str
    verifyingKey: str


class _SigningObjectCondition(_Condition):
    signing_object_context_var: str


#
# SigningObjectAttributeCondition represents:
# {
#     "attributeName": str
#     "objectContextVar": str
#     "returnValueTest: <>
# }
class SigningObjectAttributeCondition(_SigningObjectCondition):
    attributeName: str
    returnValueTest: ReturnValueTestDict


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
# - ECDSACondition
# - SigningObjectAttributeCondition
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
    AddressAllowlistConditionDict,
    ECDSAConditionDict,
    SigningObjectAttributeCondition,
]


#
# Lingo is:
# - version
# - condition
#     - ConditionDict
class Lingo(TypedDict):
    version: str
    condition: ConditionDict
