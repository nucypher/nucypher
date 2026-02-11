import decimal
import re
from collections import OrderedDict
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional, T, Tuple, Union

from eth_utils import currency
from marshmallow import Schema, post_dump
from marshmallow.exceptions import SCHEMA
from web3 import Web3

from nucypher.policy import conditions
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
from nucypher.utilities.endpoint import (
    RPCEndpoint,
    RPCEndpointManager,
    ThreadLocalSessionManager,
)
from nucypher.utilities.logging import Logger

__LOGGER = Logger("condition-eval")


def _eth_to_wei(value) -> int:
    try:
        return currency.to_wei(value, "ether")
    except decimal.InvalidOperation as e:
        raise TypeError(f"Invalid value for ethToWei conversion: {value}") from e


def _wei_to_eth(value) -> Union[int, decimal.Decimal]:
    try:
        return currency.from_wei(value, "ether")
    except decimal.InvalidOperation as e:
        raise TypeError(f"Invalid value for weiToEth conversion: {value}") from e


def _to_token_base_units(value, decimals: int) -> int:
    """
    Convert token amount to base units.

    For example, 1.5 tokens with 18 decimals -> 1500000000000000000.

    This is similar to ethToWei but allows specifying custom decimals for any token.
    Returns int to avoid float precision issues with high-precision token amounts.

    :param value: Token amount (can be int, float, or Decimal)
    :param decimals: Number of decimal places for the token (e.g., 18 for ETH, 6 for USDC)
    :return: Token amount in base units as an integer
    :raises TypeError: If value cannot be converted
    """
    try:
        from decimal import Decimal, localcontext

        with localcontext() as ctx:
            ctx.prec = 999
            # Convert to Decimal using string representation to preserve precision
            if isinstance(value, float):
                d_value = Decimal(str(value))
            elif isinstance(value, Decimal):
                d_value = value
            else:
                d_value = Decimal(value)
            result = d_value * (Decimal(10) ** decimals)
            return int(result)
    except (decimal.InvalidOperation, ValueError, TypeError) as e:
        raise TypeError(
            f"Invalid value for toTokenBaseUnits conversion: {value}"
        ) from e


def _convert_any_floats_to_decimal(value: Union[Any, List[Any], Dict[Any, Any]]) -> Any:
    """
    Convert float values to Decimal to avoid precision issues.
    """
    if isinstance(value, list):
        return [_convert_any_floats_to_decimal(item) for item in value]
    elif isinstance(value, dict):
        return {k: _convert_any_floats_to_decimal(v) for k, v in value.items()}
    elif isinstance(value, float):
        return decimal.Decimal(str(value))
    else:
        return value


def _convert_any_decimals_to_floats(
    value: Union[Any, List[Any], Dict[Any, Any]],
) -> Any:
    """
    Convert decimal values back to float.

    - Decimal is really internal
    - Conditions don't use Decimal for comparison
    - Can't use Decimal with ast.literal_eval for evaluation of conditions
    - Decimal isn't JSON serializable if reused as a ConditionVariable

    so convert back to float; loses precision after ~17 digits:
        >>> from decimal import Decimal
        >>> d = Decimal('12345678901234567890.123456789012345678')
        >>> f = float(d)
        >>> print(f)
        1.2345678901234567e+19
    """
    if isinstance(value, list):
        return [_convert_any_decimals_to_floats(item) for item in value]
    elif isinstance(value, dict):
        return {k: _convert_any_decimals_to_floats(v) for k, v in value.items()}
    elif isinstance(value, decimal.Decimal):
        return float(value)
    else:
        return value


class ConditionProviderManager:
    """
    Concurrency-friendly RPC endpoint manager
      - Manages use of multiple endpoints with a bias to preferred endpoints
      - On errors, moves on to a different endpoint.
    """

    def __init__(
        self,
        providers: Dict[int, List[str]],
        preferential_providers: Optional[Dict[int, List[str]]] = None,
    ):
        self.session_manager = ThreadLocalSessionManager()
        self.rpc_endpoint_managers = dict()

        preferential_providers = preferential_providers or {}
        for chain_id, endpoint_list in preferential_providers.items():
            preferred_providers = preferential_providers[chain_id]
            other_providers = providers.get(chain_id, [])

            if set(preferred_providers) & set(other_providers):
                raise ValueError(
                    f"Preferential providers for chain ID {chain_id} cannot overlap with other providers"
                )

            self.rpc_endpoint_managers[chain_id] = RPCEndpointManager(
                session_manager=self.session_manager,
                preferred_endpoints=preferred_providers,
                endpoints=other_providers,
            )

        for chaid_id, endpoint_list in providers.items():
            # not already in endpoint managers from preferential providers
            if chaid_id not in self.rpc_endpoint_managers:
                self.rpc_endpoint_managers[chaid_id] = RPCEndpointManager(
                    session_manager=self.session_manager,
                    endpoints=endpoint_list,
                )

        self.logger = Logger(__name__)

    @staticmethod
    def _sort_by_latency(stats: RPCEndpoint.EndpointStats) -> Tuple:
        return (stats.ewma_latency_ms,)

    def exec_web3_call(
        self,
        chain_id: int,
        fn: Callable[[Web3], T],
        request_timeout: Union[float, Tuple[float, float]] = 5.0,
    ):
        manager = self.rpc_endpoint_managers.get(chain_id, None)
        if not manager:
            raise NoConnectionToChain(chain=chain_id)

        return manager.call(
            fn=fn,
            request_timeout=request_timeout,
            endpoint_sort_strategy=self._sort_by_latency,
        )


class ConditionEvalError(Exception):
    """Exception when execution condition evaluation."""
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code


def to_camelcase(s):
    parts = iter(s.split("_"))
    return next(parts) + "".join(i.title() for i in parts)


def camel_case_to_snake(data: str) -> str:
    data = re.sub(r"(?<!^)(?=[A-Z])", "_", data).lower()
    return data


def is_camel_case(data: str) -> bool:
    # Must start with lowercase, contain no underscores/spaces, and have at least one uppercase after the first char
    return bool(re.fullmatch(r"[a-z]+(?:[A-Z][a-z0-9]*)*", data))


class CamelCaseSchema(Schema):
    """Schema that uses camel-case for its external representation
    and snake-case for its internal representation.
    """

    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = to_camelcase(field_obj.data_key or field_name)

    @post_dump
    def remove_none_for_optional_fields(self, data, **kwargs):
        # only include None values for required fields
        return {
            key: value
            for key, value in data.items()
            if value is not None or self.fields[camel_case_to_snake(key)].required
        }


def evaluate_condition_lingo(
    condition_lingo: Lingo,
    providers: Optional[ConditionProviderManager] = None,
    context: Optional[ContextDict] = None,
    log: Logger = __LOGGER,
    debug_mode: bool = False,
):
    """
    Evaluates condition lingo with the give providers and user supplied context.
    If all conditions are satisfied this function returns None.

    Args:
        condition_lingo: The condition lingo to evaluate.
        providers: Provider manager for blockchain connections.
        context: User-supplied context variables.
        log: Logger instance.
        debug_mode: If True and evaluation fails, log detailed failure information.

    # TODO: Evaluate all conditions even if one fails and report the result
    """

    # prevent circular import
    from nucypher.policy.conditions.lingo import ConditionLingo

    # Setup (don't use mutable defaults)
    context = context or dict()
    providers = providers or ConditionProviderManager(providers=dict())
    error = None

    # Evaluate
    try:
        if condition_lingo:
            lingo = ConditionLingo.from_dict(condition_lingo)
            log.debug(
                f"Evaluating access conditions for lingo id#{str(lingo.id)}: {condition_lingo}"
            )

            result = lingo.eval(debug_mode=debug_mode, providers=providers, **context)
            if not result:
                # explicit condition failure
                error = ConditionEvalError(
                    "Conditions not satisfied", HTTPStatus.FORBIDDEN
                )
    except ReturnValueEvaluationError as e:
        error = ConditionEvalError(
            f"Unable to evaluate return value: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except InvalidConditionLingo as e:
        error = ConditionEvalError(
            f"Invalid condition grammar: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except InvalidCondition as e:
        error = ConditionEvalError(
            f"Incorrect value provided for condition: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except RequiredContextVariable as e:
        # TODO: be more specific and name the missing inputs, etc
        error = ConditionEvalError(
            f"Missing required inputs: {e}", HTTPStatus.BAD_REQUEST
        )
    except InvalidContextVariableData as e:
        error = ConditionEvalError(
            f"Invalid data provided for context variable: {e}",
            HTTPStatus.BAD_REQUEST,
        )
    except ContextVariableVerificationFailed as e:
        error = ConditionEvalError(
            f"Context variable data could not be verified: {e}",
            HTTPStatus.FORBIDDEN,
        )
    except NoConnectionToChain as e:
        error = ConditionEvalError(
            f"Node does not have a connection to chain ID {e.chain}",
            HTTPStatus.NOT_IMPLEMENTED,
        )
    except ConditionEvaluationFailed as e:
        error = ConditionEvalError(
            f"Decryption condition not evaluated: {e}", HTTPStatus.BAD_REQUEST
        )
    except Exception as e:
        # TODO: Unsure why we ended up here
        message = (
            f"Unexpected exception while evaluating "
            f"decryption condition ({e.__class__.__name__}): {e}"
        )
        error = ConditionEvalError(message, HTTPStatus.INTERNAL_SERVER_ERROR)
        log.warn(message)

    if error:
        log.warn(error.message)  # log error message
        raise error


def extract_single_error_message_from_schema_errors(
    errors: Dict[str, List[str]],
) -> str:
    """
    Extract single error message from Schema().validate() errors result.

    The result is only for a single error type, and only the first message string for that type.
    If there are multiple error types, only one error type is used; the first field-specific (@validates)
    error type encountered is prioritized over any schema-level-specific (@validates_schema) error.
    """
    if not errors:
        raise ValueError("Validation errors must be provided")

    # extract error type - either field-specific (preferred) or schema-specific
    error_key_to_use = None
    for error_type in list(errors.keys()):
        error_key_to_use = error_type
        if error_key_to_use != SCHEMA:
            # actual field
            break

    message = errors[error_key_to_use][0]
    message_prefix = (
        f"'{camel_case_to_snake(error_key_to_use)}' field - "
        if error_key_to_use != SCHEMA
        else ""
    )
    return f"{message_prefix}{message}"


def check_and_convert_big_int_string_to_int(value: str) -> Union[str, int]:
    """
    Check if a string is a big int string and convert it to an integer, otherwise return the string.
    """
    if re.fullmatch(r"^-?\d+n$", value):
        try:
            result = int(value[:-1])
            return result
        except ValueError:
            # ignore
            pass

    return value


def check_and_convert_any_big_ints(value: Any) -> Any:
    """
    Check if an object contains any big int strings and convert them to an integer,
    otherwise return the object.

    Expects the object to have been created from JSON so the only objects are lists or dicts.
    """
    if isinstance(value, list):
        return [check_and_convert_any_big_ints(item) for item in value]
    elif isinstance(value, dict):
        return {k: check_and_convert_any_big_ints(v) for k, v in value.items()}
    elif isinstance(value, str):
        return check_and_convert_big_int_string_to_int(value)

    return value


DEBUG_CONDITION_NOT_EVALUATED = "<not_evaluated>"
DEBUG_CONDITION_LOGICAL_CHECK = "<logical_check>"


def extract_condition_failure_details(
    condition: "conditions.base.Condition", actual_value: Any
) -> dict:
    """Extract detailed failure information from a condition evaluation."""
    # avoid circular import
    from nucypher.policy.conditions.jwt import JWTCondition
    from nucypher.policy.conditions.lingo import (
        CompoundCondition,
        IfThenElseCondition,
        MultiCondition,
        SequentialCondition,
    )

    details: dict = {
        "condition": str(condition),
    }

    # base case
    if not isinstance(condition, MultiCondition):
        # base case - leaf condition
        if not isinstance(condition, JWTCondition):
            # JWT condition returns JWT payload, let's not include that in logs
            details["value_obtained"] = actual_value

        if hasattr(condition, "return_value_test"):
            details["check_performed"] = condition.return_value_test.to_dict()
        else:
            details["check_performed"] = DEBUG_CONDITION_LOGICAL_CHECK
    else:
        # recursive case for MultiCondition
        if isinstance(condition, IfThenElseCondition):
            # special case because of logical branches, and optional else condition
            sub_conditions = _extract_if_then_else_failure_details(
                condition, actual_value
            )
        else:
            if isinstance(condition, CompoundCondition):
                details["operator"] = condition.operator

            sub_conditions = OrderedDict()
            actual_values_list = actual_value if isinstance(actual_value, list) else []
            for i, sub_condition in enumerate(condition.conditions):
                value = (
                    actual_values_list[i]
                    if i < len(actual_values_list)
                    else DEBUG_CONDITION_NOT_EVALUATED
                )

                sub_conditions[i] = extract_condition_failure_details(
                    sub_condition, value
                )

                if isinstance(condition, SequentialCondition):
                    sub_conditions[i]["var_name"] = condition.condition_variables[
                        i
                    ].var_name

        details["sub_conditions"] = sub_conditions

    return details


def _extract_if_then_else_failure_details(
    condition: "conditions.lingo.IfThenElseCondition", actual_value: Any
) -> dict:
    """Extract failure details from if-then-else conditions."""
    actual_values_list = actual_value if isinstance(actual_value, list) else []

    details = OrderedDict()
    details["if_condition"] = extract_condition_failure_details(
        condition.if_condition,
        (
            actual_values_list[0]
            if actual_values_list
            else DEBUG_CONDITION_NOT_EVALUATED
        ),
    )
    details["then_condition"] = extract_condition_failure_details(
        # "then" is executed if there are exactly 2 values (i.e., "if" + "then")
        condition.then_condition,
        (
            actual_values_list[1]
            if len(actual_values_list) == 2
            else DEBUG_CONDITION_NOT_EVALUATED
        ),
    )

    # prevent circular import
    from nucypher.policy.conditions.base import Condition

    else_cond = condition.else_condition
    if isinstance(else_cond, Condition):
        # "else" is executed only when the values list has exactly 3 elements:
        # (if + None for "then" since "if" failed + else)
        details["else_condition"] = extract_condition_failure_details(
            else_cond,
            (
                actual_values_list[2]
                if len(actual_values_list) == 3
                else DEBUG_CONDITION_NOT_EVALUATED
            ),
        )
    else:
        details["else_condition"] = {}
        details["else_condition"]["condition"] = str(else_cond)
        if len(actual_values_list) < 3:
            details["else_condition"]["value_obtained"] = DEBUG_CONDITION_NOT_EVALUATED

    return details
