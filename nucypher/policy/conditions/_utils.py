import json
from marshmallow import Schema, post_dump
from typing import Union, Type, Dict

_ETH = 'eth_'


def to_camelcase(s):
    parts = iter(s.split("_"))
    return next(parts) + "".join(i.title() for i in parts)


class CamelCaseSchema(Schema):
    """Schema that uses camel-case for its external representation
    and snake-case for its internal representation.
    """

    SKIP_VALUES = tuple()

    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = to_camelcase(field_obj.data_key or field_name)

    @post_dump
    def remove_skip_values(self, data, **kwargs):
        return {
            key: value for key, value in data.items()
            if value not in self.SKIP_VALUES
        }


def _resolve_condition_lingo(json_data) -> Union[Type['Operator'], Type['ReencryptionCondition']]:
    """
    TODO: This feels like a jenky way to resolve data types from JSON blobs, but it works.
    Inspects a given bloc of JSON and attempts to resolve it's intended  datatype within the
    conditions expression framework.
    """
    # TODO: This is ugly but avoids circular imports :-|
    from nucypher.policy.conditions.time import TimeCondition
    from nucypher.policy.conditions.evm import ContractCondition
    from nucypher.policy.conditions.evm import RPCCondition
    from nucypher.policy.conditions.lingo import Operator

    # Inspect
    method = json_data.get('method')
    operator = json_data.get('operator')
    contract = json_data.get('contractAddress')

    # Resolve
    if method:
        if method == TimeCondition.METHOD:
            return TimeCondition
        elif contract:
            return ContractCondition
        elif method.startswith(_ETH):
            return RPCCondition
    elif operator:
        return Operator
    else:
        raise Exception(f'Cannot resolve condition lingo type from data {json_data}')


def _deserialize_condition_lingo(data: Union[str, Dict[str, str]]) -> Union['Operator', 'ReencryptionCondition']:
    """Deserialization helper for condition lingo"""
    if isinstance(data, str):
        data = json.loads(data)
    lingo_class = _resolve_condition_lingo(json_data=data)
    instance = lingo_class.from_dict(data)
    return instance
