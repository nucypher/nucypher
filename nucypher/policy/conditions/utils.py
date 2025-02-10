import re
from http import HTTPStatus
from typing import Dict, Iterator, List, Optional, Tuple

from marshmallow import Schema, post_dump
from marshmallow.exceptions import SCHEMA
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware
from web3.providers import BaseProvider

from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    ContextVariableVerificationFailed,
    InvalidCondition,
    InvalidConditionLingo,
    InvalidConnectionToChain,
    InvalidContextVariableData,
    NoConnectionToChain,
    RequiredContextVariable,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.types import ContextDict, Lingo
from nucypher.utilities.logging import Logger

__LOGGER = Logger("condition-eval")


class ConditionProviderManager:
    def __init__(self, providers: Dict[int, List[HTTPProvider]]):
        self.providers = providers
        self.logger = Logger(__name__)

    def web3_endpoints(self, chain_id: int) -> Iterator[Web3]:
        rpc_providers = self.providers.get(chain_id, None)
        if not rpc_providers:
            raise NoConnectionToChain(chain=chain_id)

        iterator_returned_at_least_one = False
        for provider in rpc_providers:
            try:
                w3 = self._configure_w3(provider=provider)
                self._check_chain_id(chain_id, w3)
                yield w3
                iterator_returned_at_least_one = True
            except InvalidConnectionToChain as e:
                # don't expect to happen but must account
                # for any misconfigurations of public endpoints
                self.logger.warn(str(e))

        # if we get here, it is because there were endpoints, but issue with configuring them
        if not iterator_returned_at_least_one:
            raise NoConnectionToChain(
                chain=chain_id,
                message=f"Problematic provider endpoints for chain ID {chain_id}",
            )

    @staticmethod
    def _configure_w3(provider: BaseProvider) -> Web3:
        # Instantiate a local web3 instance
        w3 = Web3(provider)
        # inject web3 middleware to handle POA chain extra_data field.
        w3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")
        return w3

    @staticmethod
    def _check_chain_id(chain_id: int, w3: Web3) -> None:
        """
        Validates that the actual web3 provider is *actually*
        connected to the condition's chain ID by reading its RPC endpoint.
        """
        provider_chain = w3.eth.chain_id
        if provider_chain != chain_id:
            raise InvalidConnectionToChain(
                expected_chain=chain_id,
                actual_chain=provider_chain,
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


def evaluate_condition_lingo(
    condition_lingo: Lingo,
    providers: Optional[ConditionProviderManager] = None,
    context: Optional[ContextDict] = None,
    log: Logger = __LOGGER,
):
    """
    Evaluates condition lingo with the give providers and user supplied context.
    If all conditions are satisfied this function returns None.

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
            log.info(f"Evaluating access conditions {condition_lingo}")
            lingo = ConditionLingo.from_dict(condition_lingo)
            result = lingo.eval(providers=providers, **context)
            if not result:
                # explicit condition failure
                error = ConditionEvalError(
                    "Decryption conditions not satisfied", HTTPStatus.FORBIDDEN
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
        log.info(error.message)  # log error message
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
