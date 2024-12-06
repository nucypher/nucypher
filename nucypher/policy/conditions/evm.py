from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
    validates_schema,
)
from marshmallow.validate import OneOf
from typing_extensions import override
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware
from web3.providers import BaseProvider
from web3.types import ABIFunction

from nucypher.policy.conditions import STANDARD_ABI_CONTRACT_TYPES
from nucypher.policy.conditions.base import (
    ExecutionCall,
)
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    NoConnectionToChain,
    RPCExecutionFailed,
)
from nucypher.policy.conditions.lingo import (
    ConditionType,
    ExecutionCallAccessControlCondition,
    ReturnValueTest,
)
from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.policy.conditions.validation import (
    align_comparator_value_with_abi,
    get_unbound_contract_function,
    validate_contract_function_expected_return_type,
    validate_function_abi,
)

# TODO: Move this to a more appropriate location,
#  but be sure to change the mocks in tests too.
# Permitted blockchains for condition evaluation
from nucypher.utilities import logging

_CONDITION_CHAINS = {
    1: "ethereum/mainnet",
    11155111: "ethereum/sepolia",
    137: "polygon/mainnet",
    80002: "polygon/amoy",
    # TODO: Permit support for these chains
    # 100: "gnosis/mainnet",
    # 10200: "gnosis/chiado",
}


class RPCCall(ExecutionCall):
    LOG = logging.Logger(__name__)

    ALLOWED_METHODS = {
        # RPC
        "eth_getBalance": int,
    }  # TODO other allowed methods (tDEC #64)

    class Schema(ExecutionCall.Schema):
        chain = fields.Int(required=True, strict=True)
        method = fields.Str(
            required=True,
            error_messages={
                "required": "Undefined method name",
                "null": "Undefined method name",
            },
        )
        parameters = fields.List(fields.Field, required=False, allow_none=True)
        rpc_endpoint = fields.Url(required=False, relative=False, allow_none=True)

        @validates_schema
        def validate_chain(self, data, **kwargs):
            chain = data.get("chain")
            rpc_endpoint = data.get("rpc_endpoint")
            if not rpc_endpoint and chain not in _CONDITION_CHAINS:
                raise ValidationError(
                    f"chain ID {chain} is not a permitted blockchain for condition evaluation"
                )

        @validates("method")
        def validate_method(self, value):
            if value not in RPCCall.ALLOWED_METHODS:
                raise ValidationError(
                    f"'{value}' is not a permitted RPC endpoint for condition evaluation."
                )

        @post_load
        def make(self, data, **kwargs):
            return RPCCall(**data)

    def __init__(
        self,
        chain: int,
        method: str,
        parameters: Optional[List[Any]] = None,
        rpc_endpoint: Optional[str] = None,
    ):
        self.chain = chain
        self.method = method
        self.parameters = parameters
        self.rpc_endpoint = rpc_endpoint
        super().__init__()

    def _get_web3_py_function(self, w3: Web3, rpc_method: str):
        web3_py_method = camel_case_to_snake(rpc_method)
        rpc_function = getattr(
            w3.eth, web3_py_method
        )  # bind contract function (only exposes the eth API)
        return rpc_function

    def _configure_w3(self, provider: BaseProvider) -> Web3:
        # Instantiate a local web3 instance
        w3 = Web3(provider)
        # inject web3 middleware to handle POA chain extra_data field.
        w3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")
        return w3

    def _check_chain_id(self, w3: Web3) -> None:
        """
        Validates that the actual web3 provider is *actually*
        connected to the condition's chain ID by reading its RPC endpoint.
        """
        provider_chain = w3.eth.chain_id
        if provider_chain != self.chain:
            raise NoConnectionToChain(
                chain=self.chain,
                message=f"This rpc call can only be evaluated on chain ID {self.chain} but the provider's "
                f"connection is to chain ID {provider_chain}",
            )

    def _next_endpoint(
        self, providers: Dict[int, Set[HTTPProvider]]
    ) -> Iterator[HTTPProvider]:
        """Yields the next web3 provider to try for a given chain ID"""
        try:
            rpc_providers = providers[self.chain]

        # if there are no entries for the chain ID, there
        # is no connection to that chain available.
        except KeyError:
            raise NoConnectionToChain(chain=self.chain)
        if not rpc_providers:
            raise NoConnectionToChain(chain=self.chain)  # TODO: unreachable?
        for provider in rpc_providers:
            # Someday, we might make this whole function async, and then we can knock on
            # each endpoint here to see if it's alive and only yield it if it is.
            yield provider

    def _execute_with_provider(
        self,
        provider: HTTPProvider,
        resolved_parameters: List[Any],
    ) -> Any:
        w3 = self._configure_w3(provider)
        self._check_chain_id(w3)
        return self._execute(w3, resolved_parameters)

    def execute(self, providers: Dict[int, Set[HTTPProvider]], **context) -> Any:
        resolved_parameters = []
        if self.parameters:
            resolved_parameters = resolve_any_context_variables(
                self.parameters, **context
            )

        latest_error = None
        # use local rpc endpoint if available
        if self.chain in providers:
            for provider in self._next_endpoint(providers=providers):
                try:
                    result = self._execute_with_provider(provider, resolved_parameters)
                    return result
                except Exception as e:
                    latest_error = str(e)
                    continue

            raise RPCExecutionFailed(
                f"RPC call '{self.method}' failed; latest error - {latest_error}"
            )

        # Try custom RPC endpoint if provided
        if self.rpc_endpoint:
            try:
                result = self._execute_with_provider(
                    HTTPProvider(self.rpc_endpoint), resolved_parameters
                )
                return result
            except Exception as e:
                latest_error = str(e)

        # If we get here, all attempts failed
        if latest_error:
            raise RPCExecutionFailed(
                f"RPC call '{self.method}' failed; latest error - {latest_error}"
            )
        raise NoConnectionToChain(chain=self.chain)

    def _execute(self, w3: Web3, resolved_parameters: List[Any]) -> Any:
        """Execute onchain read and return result and error if any."""
        rpc_endpoint_, rpc_method = self.method.split("_", 1)
        rpc_function = self._get_web3_py_function(w3, rpc_method)
        rpc_result = rpc_function(*resolved_parameters)  # RPC read
        return rpc_result


class RPCCondition(ExecutionCallAccessControlCondition):
    EXECUTION_CALL_TYPE = RPCCall
    CONDITION_TYPE = ConditionType.RPC.value

    class Schema(ExecutionCallAccessControlCondition.Schema, RPCCall.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.RPC.value), required=True
        )

        @validates_schema()
        def validate_expected_return_type(self, data, **kwargs):
            method = data.get("method")
            return_value_test = data.get("return_value_test")

            expected_return_type = RPCCall.ALLOWED_METHODS[method]
            comparator_value = return_value_test.value
            if is_context_variable(comparator_value):
                return

            if not isinstance(return_value_test.value, expected_return_type):
                raise ValidationError(
                    field_name="return_value_test",
                    message=f"Return value comparison for '{method}' call output "
                    f"should be '{expected_return_type}' and not '{type(comparator_value)}'.",
                )

        @post_load
        def make(self, data, **kwargs):
            return RPCCondition(**data)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(function={self.method}, chain={self.chain})"
        return r

    def __init__(
        self,
        chain: int,
        method: str,
        return_value_test: ReturnValueTest,
        condition_type: str = ConditionType.RPC.value,
        name: Optional[str] = None,
        parameters: Optional[List[Any]] = None,
        rpc_endpoint: Optional[str] = None,
        *args,
        **kwargs,
    ):
        super().__init__(
            chain=chain,
            method=method,
            return_value_test=return_value_test,
            condition_type=condition_type,
            name=name,
            parameters=parameters,
            rpc_endpoint=rpc_endpoint,
            *args,
            **kwargs,
        )

    @property
    def method(self):
        return self.execution_call.method

    @property
    def chain(self):
        return self.execution_call.chain

    @property
    def parameters(self):
        return self.execution_call.parameters

    @property
    def rpc_endpoint(self):
        return self.execution_call.rpc_endpoint

    def _align_comparator_value_with_abi(
        self, return_value_test: ReturnValueTest
    ) -> ReturnValueTest:
        return return_value_test

    def verify(
        self, providers: Dict[int, Set[HTTPProvider]], **context
    ) -> Tuple[bool, Any]:
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        return_value_test = self._align_comparator_value_with_abi(
            resolved_return_value_test
        )

        result = self.execution_call.execute(providers=providers, **context)

        eval_result = return_value_test.eval(result)  # test
        return eval_result, result


class ContractCall(RPCCall):
    class Schema(RPCCall.Schema):
        contract_address = fields.Str(required=True)
        standard_contract_type = fields.Str(
            required=False,
            validate=OneOf(
                STANDARD_ABI_CONTRACT_TYPES,
                error="Invalid standard contract type: {input}",
            ),
            allow_none=True,
        )
        function_abi = fields.Dict(required=False, allow_none=True)

        @post_load
        def make(self, data, **kwargs):
            return ContractCall(**data)

        @validates("contract_address")
        def validate_contract_address(self, value):
            try:
                to_checksum_address(value)
            except ValueError:
                raise ValidationError(f"Invalid checksum address: '{value}'")

        @override
        @validates("method")
        def validate_method(self, value):
            return

        @validates("function_abi")
        def validate_abi(self, value):
            # needs to be done before schema validation
            if value:
                try:
                    validate_function_abi(value)
                except ValueError as e:
                    raise ValidationError(
                        field_name="function_abi", message=str(e)
                    ) from e

        @validates_schema
        def validate_standard_contract_type_or_function_abi(self, data, **kwargs):
            method = data.get("method")
            standard_contract_type = data.get("standard_contract_type")
            function_abi = data.get("function_abi")

            # validate xor of standard contract type and function abi
            if not (bool(standard_contract_type) ^ bool(function_abi)):
                raise ValidationError(
                    field_name="standard_contract_type",
                    message=f"Provide a standard contract type or function ABI; got ({standard_contract_type}, {function_abi}).",
                )

            # validate function abi with method name (not available for field validation)
            if function_abi:
                try:
                    validate_function_abi(function_abi, method_name=method)
                except ValueError as e:
                    raise ValidationError(
                        field_name="function_abi", message=str(e)
                    ) from e

            # validate contract
            contract_address = to_checksum_address(data.get("contract_address"))
            try:
                get_unbound_contract_function(
                    contract_address=contract_address,
                    method=method,
                    standard_contract_type=standard_contract_type,
                    function_abi=function_abi,
                )
            except ValueError as e:
                raise ValidationError(str(e)) from e

    def __init__(
        self,
        method: str,
        contract_address: ChecksumAddress,
        standard_contract_type: Optional[str] = None,
        function_abi: Optional[ABIFunction] = None,
        *args,
        **kwargs,
    ):
        # preprocessing
        contract_address = to_checksum_address(contract_address)
        self.contract_address = contract_address
        self.standard_contract_type = standard_contract_type
        self.function_abi = function_abi

        super().__init__(method=method, *args, **kwargs)

        # contract function already validated - so should not raise an exception
        self.contract_function = get_unbound_contract_function(
            contract_address=self.contract_address,
            method=self.method,
            standard_contract_type=self.standard_contract_type,
            function_abi=self.function_abi,
        )

    def _execute(self, w3: Web3, resolved_parameters: List[Any]) -> Any:
        """Execute onchain read and return result."""
        self.contract_function.w3 = w3
        bound_contract_function = self.contract_function(
            *resolved_parameters
        )  # bind contract function
        contract_result = bound_contract_function.call()  # onchain read
        return contract_result


class ContractCondition(RPCCondition):
    EXECUTION_CALL_TYPE = ContractCall
    CONDITION_TYPE = ConditionType.CONTRACT.value

    class Schema(RPCCondition.Schema, ContractCall.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.CONTRACT.value), required=True
        )

        @validates_schema()
        def validate_expected_return_type(self, data, **kwargs):
            # validate that contract function is correct
            try:
                contract_function = get_unbound_contract_function(
                    contract_address=data.get("contract_address"),
                    method=data.get("method"),
                    standard_contract_type=data.get("standard_contract_type"),
                    function_abi=data.get("function_abi"),
                )
            except ValueError as e:
                raise ValidationError(str(e)) from e

            # validate return type based on contract function
            return_value_test = data.get("return_value_test")
            try:
                validate_contract_function_expected_return_type(
                    contract_function=contract_function,
                    return_value_test=return_value_test,
                )
            except ValueError as e:
                raise ValidationError(
                    field_name="return_value_test",
                    message=str(e),
                ) from e

        @post_load
        def make(self, data, **kwargs):
            return ContractCondition(**data)

    def __init__(
        self,
        method: str,
        contract_address: ChecksumAddress,
        condition_type: str = ConditionType.CONTRACT.value,
        standard_contract_type: Optional[str] = None,
        function_abi: Optional[ABIFunction] = None,
        *args,
        **kwargs,
    ):
        super().__init__(
            method=method,
            condition_type=condition_type,
            contract_address=contract_address,
            standard_contract_type=standard_contract_type,
            function_abi=function_abi,
            *args,
            **kwargs,
        )

    @property
    def function_abi(self):
        return self.execution_call.function_abi

    @property
    def standard_contract_type(self):
        return self.execution_call.standard_contract_type

    @property
    def contract_function(self):
        return self.execution_call.contract_function

    @property
    def contract_address(self):
        return self.execution_call.contract_address

    def __repr__(self) -> str:
        r = (
            f"{self.__class__.__name__}(function={self.method}, "
            f"contract={self.contract_address}, "
            f"chain={self.chain})"
        )
        return r

    def _align_comparator_value_with_abi(
        self, return_value_test: ReturnValueTest
    ) -> ReturnValueTest:
        return align_comparator_value_with_abi(
            abi=self.contract_function.contract_abi[0],
            return_value_test=return_value_test,
        )
