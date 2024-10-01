from typing import Any, List, Optional

from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)
from typing_extensions import override
from web3 import Web3

from nucypher.policy.conditions.evm import RPCCall, RPCCondition
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest


class TimeRPCCall(RPCCall):
    METHOD = "blocktime"

    class Schema(RPCCall.Schema):
        method = fields.Str(dump_default="blocktime", required=True)

        @override
        @validates("method")
        def validate_method(self, value):
            if value != TimeRPCCall.METHOD:
                raise ValidationError(f"method name must be {TimeRPCCall.METHOD}.")

        @validates("parameters")
        def validate_no_parameters(self, value):
            if value:
                raise ValidationError(
                    f"{TimeRPCCall.METHOD}' does not take any parameters"
                )

        @post_load
        def make(self, data, **kwargs):
            return TimeRPCCall(**data)

    def __init__(
        self,
        chain: int,
        method: str = METHOD,
        parameters: Optional[List[Any]] = None,
    ):
        super().__init__(chain=chain, method=method, parameters=parameters)

    def _execute(self, w3: Web3, resolved_parameters: List[Any]) -> Any:
        """Execute onchain read and return result."""
        # TODO may need to rethink as part of #3051 (multicall work).
        latest_block = w3.eth.get_block("latest")
        return latest_block.timestamp


class TimeCondition(RPCCondition):
    EXECUTION_CALL_TYPE = TimeRPCCall
    CONDITION_TYPE = ConditionType.TIME.value

    class Schema(RPCCondition.Schema, TimeRPCCall.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.TIME.value), required=True
        )

        @validates_schema
        def validate_expected_return_type(self, data, **kwargs):
            return_value_test = data.get("return_value_test")
            comparator_value = return_value_test.value
            if not isinstance(comparator_value, int):
                raise ValidationError(
                    field_name="return_value_test",
                    message=f"Invalid return value comparison type '{type(comparator_value)}'; must be an integer",
                )

        @post_load
        def make(self, data, **kwargs):
            return TimeCondition(**data)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(timestamp={self.return_value_test.value}, chain={self.chain})"
        return r

    def __init__(
        self,
        return_value_test: ReturnValueTest,
        chain: int,
        method: str = TimeRPCCall.METHOD,
        condition_type: str = ConditionType.TIME.value,
        name: Optional[str] = None,
    ):
        # call to super must be at the end for proper validation
        super().__init__(
            return_value_test=return_value_test,
            chain=chain,
            method=method,
            condition_type=condition_type,
            name=name,
        )

    @property
    def timestamp(self):
        return self.return_value_test.value
