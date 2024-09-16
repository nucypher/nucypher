from typing import Any, List, Optional

from marshmallow import fields, post_load, validate
from marshmallow.validate import Equal
from web3 import Web3

from nucypher.policy.conditions.base import ExecutionCall
from nucypher.policy.conditions.evm import RPCCall, RPCCondition
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import ConditionType


class TimeRPCCall(RPCCall):
    METHOD = "blocktime"

    def __init__(
        self,
        chain: int,
        method: str = METHOD,
        parameters: Optional[List[Any]] = None,
    ):
        if parameters:
            raise ValueError(f"{self.METHOD} does not take any parameters")

        super().__init__(chain=chain, method=method, parameters=parameters)

    def _validate_method(self, method):
        if method != self.METHOD:
            raise ValueError(
                f"{self.__class__.__name__} must be instantiated with the {self.METHOD} method."
            )
        return method

    def _execute(self, w3: Web3, resolved_parameters: List[Any]) -> Any:
        """Execute onchain read and return result."""
        # TODO may need to rethink as part of #3051 (multicall work).
        latest_block = w3.eth.get_block("latest")
        return latest_block.timestamp


class TimeCondition(RPCCondition):
    CONDITION_TYPE = ConditionType.TIME.value

    class Schema(RPCCondition.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.TIME.value), required=True
        )
        method = fields.Str(
            dump_default="blocktime", required=True, validate=Equal("blocktime")
        )

        @post_load
        def make(self, data, **kwargs):
            return TimeCondition(**data)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(timestamp={self.return_value_test.value}, chain={self.chain})"
        return r

    def __init__(
        self,
        method: str = TimeRPCCall.METHOD,
        condition_type: str = CONDITION_TYPE,
        *args,
        **kwargs,
    ):
        # call to super must be at the end for proper validation
        super().__init__(
            condition_type=condition_type,
            method=method,
            *args,
            **kwargs,
        )

    def _create_execution_call(self, *args, **kwargs) -> ExecutionCall:
        return TimeRPCCall(*args, **kwargs)

    def _validate_expected_return_type(self):
        comparator_value = self.return_value_test.value
        if not isinstance(comparator_value, int):
            raise InvalidCondition(
                f"Invalid return value comparison type '{type(comparator_value)}'; must be an integer"
            )

    @property
    def timestamp(self):
        return self.return_value_test.value
