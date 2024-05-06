from typing import Any, List, Optional

from marshmallow import fields, post_load, validate
from marshmallow.validate import Equal, OneOf

# from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import _CONDITION_CHAINS, RPCCondition
from nucypher.policy.conditions.exceptions import (
    # UserAddressException,
    InvalidCondition,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import CamelCaseSchema


class AddressMatchCondition(RPCCondition):
    METHOD = "address_match"
    CONDITION_TYPE = ConditionType.ADDRESS.value

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ADDRESS.value), required=True
        )
        name = fields.Str(required=False)
        chain = fields.Int(
            required=True, strict=True, validate=OneOf(_CONDITION_CHAINS)
        )
        method = fields.Str(
            dump_default="address_match", required=True, validate=Equal("address_match")
        )
        parameters = fields.List(fields.Field, attribute="parameters", required=False)
        return_value_test = fields.Nested(
            ReturnValueTest.ReturnValueTestSchema(), required=True
        )

        @post_load
        def make(self, data, **kwargs):
            return AddressMatchCondition(**data)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(address={self.return_value_test.value}, chain={self.chain})"
        return r

    def __init__(
        self,
        return_value_test: ReturnValueTest,
        chain: int,
        method: str = METHOD,
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
        parameters: Optional[List[Any]] = None,
    ):
        if method != self.METHOD:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.METHOD} method."
            )

        if not parameters:
            raise ValueError("No parameters provided.")

        # TODO: improve safty on parameter
        # if len(parameters[0]) != 42:
        #     raise AddressLengthException(parameters[0])
        # if parameters[0] != USER_ADDRESS_CONTEXT:
        #     raise UserAddressException(parameters[0])

        # call to super must be at the end for proper validation
        super().__init__(
            chain=chain,
            method=method,
            return_value_test=return_value_test,
            name=name,
            condition_type=condition_type,
            parameters=parameters,
        )

    def _validate_method(self, method):
        return method

    def _validate_expected_return_type(self):
        comparator_value = self.return_value_test.value
        if not isinstance(comparator_value, str):
            raise InvalidCondition(
                f"Invalid return value comparison type '{type(comparator_value)}'; must be a string"
            )

    @property
    def address(self):
        return self.return_value_test.value

    def _execute_call(self, parameters: List[Any]) -> Any:
        """Execute non onchain read and return result."""
        return parameters[0]
