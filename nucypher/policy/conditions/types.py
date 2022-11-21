from typing import Dict, List, Union

ConditionValues = Union[str, int, bool]
ReturnValueDict = Dict[str, ConditionValues]
ConditionDict = Dict[str, Union[ConditionValues, ReturnValueDict]]
LingoList = List[ConditionDict]
