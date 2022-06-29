import json
from typing import List, Dict

from eth_typing import ChecksumAddress
from marshmallow import fields, post_load
from web3 import HTTPProvider

from nucypher.policy.conditions.payment import ReturnValueTest
from nucypher.policy.conditions import ReencryptionCondition
from nucypher.policy.conditions.base import CamelCaseSchema


STANDARD_ABIS = {
    'ERC20': []
}


def authenticate(self, signature):
    # TODO: Authenticate
    return


class EVMCondition(ReencryptionCondition):

    DIRECTIVES = {
        ':userAddress': authenticate
    }

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

        self.chain = chain
        self.method = method
        self.standard_contract_type = standard_contract_type
        self.contract_address = contract_address
        self.function_name = function_name
        self.function_abi = function_abi
        self.parameters = parameters
        self.return_value_test = return_value_test

    def verify(self,
               providers: Dict[str, HTTPProvider],
               requester_address: ChecksumAddress,
               *args, **kwargs
               ) -> bool:

        provider = providers[self.chain]
        abi = self.function_abi or STANDARD_ABIS[self.standard_contract_type]
        contract = provider.w3.eth.contract(address=self.contract_address, abi=abi)
        contract_function = getattr(contract.functions, self.function_name)
        contract_result = contract_function.call(*self.parameters)
        eval_result = self.return_value_test.eval(contract_result)
        return eval_result
