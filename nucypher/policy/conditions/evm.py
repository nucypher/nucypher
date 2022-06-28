import json
from typing import List

from marshmallow import fields, post_load

from nucypher.policy.conditions.payment import ReturnValueTest
from nucypher.policy.conditions import ReencryptionCondition
from nucypher.policy.conditions.base import CamelCaseSchema


class EVMCondition(ReencryptionCondition):
    class Schema(CamelCaseSchema):
        name = fields.Str()
        chain = fields.Str()
        method = fields.Str()
        standard_contract_type = fields.Str(required=False)
        contract_address = fields.Str(required=False)
        parameters = fields.List(fields.String, attribute='parameters')
        return_value_test = fields.Nested(ReturnValueTest.ReturnValueTestSchema())
        function_name = fields.Str(required=False)
        function_abi = fields.Str(required=False)

        @post_load
        def make(self, data, **kwargs):
            return EVMCondition(**data)

    def __init__(self,
                 chain: str,
                 method: str,
                 standard_contract_type: str,
                 contract_address: str,
                 parameters: List[str],
                 return_value_test: ReturnValueTest,
                 function_name: str = None,
                 function_abi: str = None):

        # common
        self.chain = chain
        self.method = method
        self.standard_contract_type = standard_contract_type
        self.contract_address = contract_address
        self.parameters = parameters
        self.return_value_test = return_value_test

        # for custom contract calls
        self.function_name = function_name
        self.function_abi = function_abi

    def verify(self, *args, **kwargs) -> bool:
        return True
