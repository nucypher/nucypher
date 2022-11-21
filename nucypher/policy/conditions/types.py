import sys

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

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
    operator: str


#
# ConditionDict is a dictionary of:
# - str -> Simple values (str, int, bool), or parameter list which can be anything ('Any')
# - "returnValueTest" -> Return Value Test definitions
# - "functionAbi" -> ABI function definitions (already defined by web3)
#
BaseValue = Union[str, int, bool]
MethodParameters = List[Any]

ConditionValue = Union[BaseValue, MethodParameters]  # base value or list of base values


# Return Value Test
class ReturnValueTestDict(TypedDict, total=False):
    comparator: str
    value: Any
    key: Union[str, int]


ConditionDict = Dict[str, Union[ConditionValue, ReturnValueTestDict, ABIFunction]]

#
# LingoEntry is:
# - Condition
# - Operator
#
LingoEntry = Union[OperatorDict, ConditionDict]

#
# LingoList contains a list of LingoEntries
LingoList = List[LingoEntry]


#
# Object Types
#
LingoEntryObjectType = Union[Type["Operator"], Type["ReencryptionCondition"]]
LingoEntryObject = Union["Operator", "ReencryptionCondition"]
