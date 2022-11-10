"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import json
from http import HTTPStatus
from typing import Dict, Optional, Tuple, Type, Union

from marshmallow import Schema, post_dump
from web3.providers import BaseProvider

from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    ContextVariableVerificationFailed,
    InvalidCondition,
    InvalidContextVariableData,
    NoConnectionToChain,
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
    from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
    from nucypher.policy.conditions.lingo import Operator
    from nucypher.policy.conditions.time import TimeCondition

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


def evaluate_conditions(
    lingo: "ConditionLingo",
    providers: Optional[Dict[str, BaseProvider]] = None,
    context: Optional[Dict[Union[str, int], Union[str, int]]] = None,
    log: Logger = __LOGGER,
) -> Optional[Tuple[str, HTTPStatus]]:

    # avoid using a mutable defaults and support federated mode
    context = context or dict()
    providers = providers or dict()
    error = None
    if lingo is not None:
        # TODO: Evaluate all conditions even if one fails and report the result
        try:
            log.info(f"Evaluating access conditions {lingo}")
            result = lingo.eval(providers=providers, **context)
            if not result:
                # explicit condition failure
                error = ("Decryption conditions not satisfied", HTTPStatus.FORBIDDEN)
        except InvalidCondition as e:
            error = (
                f"Incorrect value provided for condition: {e}",
                HTTPStatus.BAD_REQUEST,
            )
        except RequiredContextVariable as e:
            # TODO: be more specific and name the missing inputs, etc
            error = (f"Missing required inputs: {e}", HTTPStatus.BAD_REQUEST)
        except InvalidContextVariableData as e:
            error = (
                f"Invalid data provided for context variable: {e}",
                HTTPStatus.BAD_REQUEST,
            )
        except ContextVariableVerificationFailed as e:
            error = (
                f"Context variable data could not be verified: {e}",
                HTTPStatus.FORBIDDEN,
            )
        except NoConnectionToChain as e:
            error = (
                f"Node does not have a connection to chain ID {e.chain}: {e}",
                HTTPStatus.NOT_IMPLEMENTED,
            )
        except ConditionEvaluationFailed as e:
            error = (
                f"Decryption condition not evaluated: {e}",
                HTTPStatus.BAD_REQUEST
            )
        except Exception as e:
            # TODO: Unsure why we ended up here
            message = f"Unexpected exception while evaluating " \
                      f"decryption condition ({e.__class__.__name__}): {e}"
            error = (message, HTTPStatus.INTERNAL_SERVER_ERROR)
            log.warn(message)

    if error:
        log.info(error[0])  # log error message

    return error
