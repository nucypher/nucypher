import json
import re
from http import HTTPStatus
from typing import Dict, NamedTuple, Optional, Type, Union

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
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ConditionDict, LingoList
from nucypher.utilities.logging import Logger

_ETH = "eth_"
__LOGGER = Logger("condition-eval")


class EvalError(NamedTuple):
    message: str
    status_code: int


def to_camelcase(s):
    parts = iter(s.split("_"))
    return next(parts) + "".join(i.title() for i in parts)


def camel_case_to_snake(data: str) -> str:
    data = re.sub(r"(?<!^)(?=[A-Z])", "_", data).lower()
    return data


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
            key: value for key, value in data.items() if value not in self.SKIP_VALUES
        }


def resolve_condition_lingo(
    data: ConditionDict,
) -> Union[Type["Operator"], Type["ReencryptionCondition"]]:
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
    method = data.get("method")
    operator = data.get("operator")
    contract = data.get("contractAddress")

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
        raise Exception(f"Cannot resolve condition lingo type from data {data}")


def deserialize_condition_lingo(
    data: Union[str, ConditionDict]
) -> Union["Operator", "ReencryptionCondition"]:
    """Deserialization helper for condition lingo"""
    if isinstance(data, str):
        data = json.loads(data)
    lingo_class = resolve_condition_lingo(data=data)
    instance = lingo_class.from_dict(data)
    return instance


def validate_condition_lingo(conditions: LingoList) -> None:
    for c in conditions:
        lingo_class = resolve_condition_lingo(data=c)
        lingo_class.validate(data=c)


def evaluate_condition_lingo(
    lingo: "ConditionLingo",
    providers: Optional[Dict[int, BaseProvider]] = None,
    context: Optional[Dict[Union[str, int], Union[str, int]]] = None,
    log: Logger = __LOGGER,
) -> Optional[EvalError]:
    """
    Evaluates condition lingo with the give providers and user supplied context.
    If all conditions are satisfied this function returns None.

    # TODO: Evaluate all conditions even if one fails and report the result
    """

    # Setup (don't use mutable defaults and support federated mode)
    context = context or dict()
    providers = providers or dict()
    error = None

    # Evaluate
    try:
        log.info(f"Evaluating access conditions {lingo}")
        result = lingo.eval(providers=providers, **context)
        if not result:
            # explicit condition failure
            error = ("Decryption conditions not satisfied", HTTPStatus.FORBIDDEN)
    except ReturnValueEvaluationError as e:
        error = (
            f"Unable to evaluate return value: {e}",
            HTTPStatus.BAD_REQUEST,
        )
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
        error = (f"Decryption condition not evaluated: {e}", HTTPStatus.BAD_REQUEST)
    except Exception as e:
        # TODO: Unsure why we ended up here
        message = (
            f"Unexpected exception while evaluating "
            f"decryption condition ({e.__class__.__name__}): {e}"
        )
        error = (message, HTTPStatus.INTERNAL_SERVER_ERROR)
        log.warn(message)

    if error:
        error = EvalError(*error)
        log.info(error.message)  # log error message

    return error
