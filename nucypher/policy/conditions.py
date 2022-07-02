import json
from base64 import b64encode, b64decode
from pathlib import Path
from typing import List, Dict
from typing import Union, Tuple

from eth_typing import ChecksumAddress
from marshmallow import Schema
from marshmallow import fields, post_load, post_dump
from web3 import HTTPProvider

STANDARD_ABIS_FILEPATH = Path(__file__).parent / 'abis.json'
with open(STANDARD_ABIS_FILEPATH, 'r') as file:
    STANDARD_ABIS = json.loads(file.read())


def authenticate(self, signature):
    # TODO: Authenticate
    return


def camelcase(s):
    parts = iter(s.split("_"))
    return next(parts) + "".join(i.title() for i in parts)


class CamelCaseSchema(Schema):
    """Schema that uses camel-case for its external representation
    and snake-case for its internal representation.
    """

    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = camelcase(field_obj.data_key or field_name)


class SerializableCondition:

    class Schema(CamelCaseSchema):
        field = NotImplemented

    @classmethod
    def from_json(cls, data) -> 'SerializableCondition':
        data = json.loads(data)
        schema = cls.Schema()
        instance = schema.load(data)
        return instance

    def to_json(self) -> str:
        schema = self.Schema()
        data = schema.dumps(self)
        return data

    def __bytes__(self) -> bytes:
        json_payload = self.to_json().encode()
        b64_json_payload = b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> 'SerializableCondition':
        json_payload = b64decode(data).decode()
        instance = cls.from_json(json_payload)
        return instance


class Operator(SerializableCondition):

    class OperatorSchema(CamelCaseSchema):
        operator = fields.Str()

        @post_load
        def make(self, data, **kwargs):
            return Operator(**data)

    def __init__(self, operator: str):
        self.operator = operator


class ReturnValueTest:

    COMPARATORS = ('==', '>', '<', '<=', '>=')

    class ReturnValueTestSchema(CamelCaseSchema):
        comparator = fields.Str()
        value = fields.Str()

        @post_load
        def make(self, data, **kwargs):
            return ReturnValueTest(**data)

    def __init__(self, comparator: str, value: Union[int, str]):
        comparator, value = self.sanitize(comparator, value)
        self.comparator = comparator
        self.value = value

    def sanitize(self, comparator: str, value: str) -> Tuple[str, str]:
        if comparator not in self.COMPARATORS:
            raise ValueError(f'{comparator} is not a permitted comparator.')
        return comparator, value

    def eval(self, data) -> bool:
        # TODO: Sanitize input
        result = eval(f'{data}{self.comparator}{self.value}')
        return result


class EVMCondition(SerializableCondition):

    DIRECTIVES = {
        ':userAddress': authenticate
    }

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None, )

        name = fields.Str()
        chain = fields.Str()
        method = fields.Str()
        standard_contract_type = fields.Str(required=False)
        contract_address = fields.Str(required=False)
        parameters = fields.List(fields.String, attribute='parameters')
        return_value_test = fields.Nested(ReturnValueTest.ReturnValueTestSchema())
        function_name = fields.Str(required=False)
        function_abi = fields.Str(required=False)

        @post_dump
        def remove_skip_values(self, data, **kwargs):
            return {
                key: value for key, value in data.items()
                if value not in self.SKIP_VALUES
            }

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
