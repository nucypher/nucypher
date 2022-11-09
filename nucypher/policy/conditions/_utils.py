import json
from http import HTTPStatus
from typing import Union, Type, Dict, Optional

from flask import Response
from marshmallow import Schema, post_dump
from web3.providers import BaseProvider

from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.context import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
)
from nucypher.utilities.logging import Logger

_ETH = 'eth_'
__LOGGER = Logger('condition-eval')


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


def evaluate_conditions_for_ursula(lingo: 'ConditionLingo',
                                   providers: Optional[Dict[str, BaseProvider]] = None,
                                   context: Optional[Dict[Union[str, int], Union[str, int]]] = None,
                                   log: Logger = __LOGGER,
                                   ) -> Response:

    # avoid using a mutable defaults and support federated mode
    context = context or dict()
    providers = providers or dict()

    if lingo is not None:
        # TODO: Evaluate all conditions even if one fails and report the result
        try:
            log.info(f'Evaluating access conditions {lingo.id}')
            _results = lingo.eval(providers=providers, **context)
        except ReencryptionCondition.InvalidCondition as e:
            message = f"Incorrect value provided for condition: {e}"
            error = (message, HTTPStatus.BAD_REQUEST)
            log.info(message)
            return Response(message, status=error[1])
        except RequiredContextVariable as e:
            message = f"Missing required inputs: {e}"
            # TODO: be more specific and name the missing inputs, etc
            error = (message, HTTPStatus.BAD_REQUEST)
            log.info(message)
            return Response(message, status=error[1])
        except InvalidContextVariableData as e:
            message = f"Invalid data provided for context variable: {e}"
            error = (message, HTTPStatus.BAD_REQUEST)
            log.info(message)
            return Response(message, status=error[1])
        except ContextVariableVerificationFailed as e:
            message = f"Context variable data could not be verified: {e}"
            error = (message, HTTPStatus.FORBIDDEN)
            log.info(message)
            return Response(message, status=error[1])
        except ReencryptionCondition.ConditionEvaluationFailed as e:
            message = f"Decryption condition not evaluated: {e}"
            error = (message, HTTPStatus.BAD_REQUEST)
            log.info(message)
            return Response(message, status=error[1])
        except lingo.Failed as e:
            # TODO: Better error reporting
            message = f"Decryption conditions not satisfied: {e}"
            error = (message, HTTPStatus.FORBIDDEN)
            log.info(message)
            return Response(message, status=error[1])
        except Exception as e:
            # TODO: Unsure why we ended up here
            message = f"Unexpected exception while evaluating " \
                      f"decryption condition ({e.__class__.__name__}): {e}"
            error = (message, HTTPStatus.INTERNAL_SERVER_ERROR)
            log.warn(message)
            return Response(message, status=error[1])
