import json
import re
from http import HTTPStatus
from typing import Dict, NamedTuple, Optional, Tuple, Type, Union

from marshmallow import Schema, ValidationError, post_dump
from web3.providers import BaseProvider

from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    ContextVariableVerificationFailed,
    InvalidCondition,
    InvalidConditionLingo,
    InvalidContextVariableData,
    NoConnectionToChain,
    RequiredContextVariable,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ContextDict, Lingo
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

    SKIP_VALUES: Tuple = tuple()

    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = to_camelcase(field_obj.data_key or field_name)

    @post_dump
    def remove_skip_values(self, data, **kwargs):
        return {
            key: value for key, value in data.items() if value not in self.SKIP_VALUES
        }


def resolve_condition_lingo(
    data: Lingo,
) -> Union[Type["CompoundAccessControlCondition"], Type["AccessControlCondition"]]:
    """
    TODO: This feels like a jenky way to resolve data types from JSON blobs, but it works.
    Inspects a given bloc of JSON and attempts to resolve it's intended  datatype within the
    conditions expression framework.
    """
    # TODO: This is ugly but avoids circular imports :-|
    from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
    from nucypher.policy.conditions.lingo import CompoundAccessControlCondition
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
        return CompoundAccessControlCondition

    raise InvalidConditionLingo(f"Cannot resolve condition lingo type from data {data}")


def deserialize_condition_lingo(
    data: Lingo,
) -> Union["CompoundAccessControlCondition", "AccessControlCondition"]:
    """Deserialization helper for condition lingo"""
    if isinstance(data, str):
        data = json.loads(data)
    lingo_class = resolve_condition_lingo(data=data)
    instance = lingo_class.from_dict(data)
    return instance


def validate_condition_lingo(condition: Lingo) -> None:
    lingo_class = resolve_condition_lingo(data=condition)
    lingo_class.validate(data=condition)


def evaluate_condition_lingo(
    condition_lingo: Lingo,
    providers: Optional[Dict[int, BaseProvider]] = None,
    context: Optional[ContextDict] = None,
    log: Logger = __LOGGER,
) -> Optional[EvalError]:
    """
    Evaluates condition lingo with the give providers and user supplied context.
    If all conditions are satisfied this function returns None.

    # TODO: Evaluate all conditions even if one fails and report the result
    """

    # prevent circular import
    from nucypher.policy.conditions.lingo import ConditionLingo

    # Setup (don't use mutable defaults)
    context = context or dict()
    providers = providers or dict()
    error = None

    # Evaluate
    try:
        if condition_lingo:
            log.info(f"Evaluating access conditions {condition_lingo}")
            lingo = ConditionLingo.from_dict(condition_lingo)
            result = lingo.eval(providers=providers, **context)
            if not result:
                # explicit condition failure
                error = EvalError(
                    "Decryption conditions not satisfied", HTTPStatus.FORBIDDEN
                )
    except ValidationError as e:
        # marshmallow Validation Error
        # TODO get this to always be InvalidConditionInfo/InvalidCondition
        #  so that this block can be removed
        error = EvalError(
            f"Invalid condition grammar: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except ReturnValueEvaluationError as e:
        error = EvalError(
            f"Unable to evaluate return value: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except InvalidConditionLingo as e:
        error = EvalError(
            f"Invalid condition grammar: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except InvalidCondition as e:
        error = EvalError(
            f"Incorrect value provided for condition: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except RequiredContextVariable as e:
        # TODO: be more specific and name the missing inputs, etc
        error = EvalError(f"Missing required inputs: {e}", HTTPStatus.BAD_REQUEST)
    except InvalidContextVariableData as e:
        error = EvalError(
            f"Invalid data provided for context variable: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except ContextVariableVerificationFailed as e:
        error = EvalError(
            f"Context variable data could not be verified: {e}",
            HTTPStatus.FORBIDDEN,
        )
    except NoConnectionToChain as e:
        error = EvalError(
            f"Node does not have a connection to chain ID {e.chain}",
            HTTPStatus.NOT_IMPLEMENTED,
        )
    except ConditionEvaluationFailed as e:
        error = EvalError(
            f"Decryption condition not evaluated: {e}", HTTPStatus.BAD_REQUEST
        )
    except Exception as e:
        # TODO: Unsure why we ended up here
        message = (
            f"Unexpected exception while evaluating "
            f"decryption condition ({e.__class__.__name__}): {e}"
        )
        error = EvalError(message, HTTPStatus.INTERNAL_SERVER_ERROR)
        log.warn(message)

    if error:
        error = EvalError(*error)
        log.info(error.message)  # log error message

    return error
