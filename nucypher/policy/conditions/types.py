from typing import Dict, List, Union

ConditionValues = Union[str, int]
ReturnValueDict = Dict[str, ConditionValues]
ConditionDict = Dict[str, Union[ConditionValues, ReturnValueDict]]
LingoList = List[ConditionDict]
