from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from marshmallow import ValidationError, fields, post_load, validate, validates_schema
from web3 import HTTPProvider, Web3
from web3.contract.contract import ContractFunction
from web3.middleware import geth_poa_middleware
from web3.providers import BaseProvider
from web3.types import ABIFunction

from nucypher.policy.conditions import STANDARD_ABI_CONTRACT_TYPES, STANDARD_ABIS
from nucypher.policy.conditions.base import AccessControlCondition, ExecutionCall
from nucypher.policy.conditions.context import (
    is_context_variable,
    resolve_parameter_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    NoConnectionToChain,
    RequiredContextVariable,
    RPCExecutionFailed,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.utils import CamelCaseSchema, camel_case_to_snake
from nucypher.policy.conditions.validation import (
    _align_comparator_value_with_abi,
    _get_abi_types,
    _validate_contract_call_abi,
    _validate_multiple_output_types,
    _validate_single_output_type,
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


def _resolve_abi(
    w3: Web3,
    method: str,
    standard_contract_type: Optional[str] = None,
    function_abi: Optional[ABIFunction] = None,
) -> ABIFunction:
    """Resolves the contract an/or function ABI from a standard contract name"""

    if not (function_abi or standard_contract_type):
        raise InvalidCondition(
            f"Ambiguous ABI - Supply either an ABI or a standard contract type ({STANDARD_ABI_CONTRACT_TYPES})."
        )

    if standard_contract_type:
        try:
            # Lookup the standard ABI given it's ERC standard name (standard contract type)
            contract_abi = STANDARD_ABIS[standard_contract_type]
        except KeyError:
            raise InvalidCondition(
                f"Invalid standard contract type {standard_contract_type}; Must be one of {STANDARD_ABI_CONTRACT_TYPES}"
            )

        try:
            # Extract all function ABIs from the contract's ABI.
            # Will raise a ValueError if there is not exactly one match.
            function_abi = (
                w3.eth.contract(abi=contract_abi).get_function_by_name(method).abi
            )
        except ValueError as e:
            raise InvalidCondition(str(e))

    return ABIFunction(function_abi)


def _validate_chain(chain: int) -> None:
    if not isinstance(chain, int):
        raise ValueError(
            f'The "chain" field of a condition must be the '
            f'integer chain ID (got "{chain}").'
        )
    if chain not in _CONDITION_CHAINS:
        raise InvalidCondition(
            f"chain ID {chain} is not a permitted "
            f"blockchain for condition evaluation."
        )


class RPCCall(ExecutionCall):
    LOG = logging.Logger(__name__)

    ALLOWED_METHODS = {
        # RPC
        "eth_getBalance": int,
    }  # TODO other allowed methods (tDEC #64)

    class Schema(ExecutionCall.Schema):
        SKIP_VALUES = (None,)
        chain = fields.Int(
            required=True, strict=True, validate=validate.OneOf(_CONDITION_CHAINS)
        )
        method = fields.Str(required=True)
        parameters = fields.List(fields.Field, attribute="parameters", required=False)

        @post_load
        def make(self, data, **kwargs):
            return RPCCall(**data)

    def __init__(
        self,
        chain: int,
        method: str,
        call_type: str = "rpc",
        parameters: Optional[List[Any]] = None,
    ):
        # Validate input
        self._validate_call_type(call_type)
        # TODO: Additional validation (function is valid for ABI, RVT validity, standard contract name validity, etc.)
        _validate_chain(chain=chain)

        self.call_type = call_type

        self.chain = chain
        self.method = self._validate_method(method=method)
        self.parameters = parameters or None

    def _validate_call_type(self, call_type):
        if call_type != "rpc":
            raise ValueError(f"Invalid execution call type: {call_type}")

    def _validate_method(self, method):
        if not method:
            raise ValueError("Undefined method name")

        if method not in self.ALLOWED_METHODS:
            raise ValueError(
                f"'{method}' is not a permitted RPC endpoint for condition evaluation."
            )
        return method

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

    def _configure_provider(self, provider: BaseProvider):
        """Binds the condition's contract function to a blockchain provider for evaluation"""
        w3 = self._configure_w3(provider=provider)
        self._check_chain_id(w3)
        return w3

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

    def execute(self, providers: Dict[int, Set[HTTPProvider]], **context) -> Any:
        resolved_parameters = resolve_parameter_context_variables(
            self.parameters, **context
        )

        endpoints = self._next_endpoint(providers=providers)
        latest_error = ""
        for provider in endpoints:
            w3 = self._configure_provider(provider)
            try:
                result = self._execute(w3, resolved_parameters)
                break
            except RequiredContextVariable:
                raise
            except Exception as e:
                latest_error = f"RPC call '{self.method}' failed: {e}"
                self.LOG.warn(f"{latest_error}, attempting to try next endpoint.")
                # Something went wrong. Try the next endpoint.
                continue
        else:
            # Fuck.
            raise RPCExecutionFailed(
                f"RPC call '{self.method}' failed; latest error - {latest_error}"
            )

        return result

    def _execute(self, w3: Web3, resolved_parameters: List[Any]) -> Any:
        """Execute onchain read and return result."""
        rpc_endpoint_, rpc_method = self.method.split("_", 1)
        rpc_function = self._get_web3_py_function(w3, rpc_method)
        rpc_result = rpc_function(*resolved_parameters)  # RPC read
        return rpc_result


class RPCCondition(AccessControlCondition):
    CONDITION_TYPE = ConditionType.RPC.value

    class Schema(RPCCall.Schema):
        name = fields.Str(required=False)
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.RPC.value), required=True
        )
        return_value_test = fields.Nested(
            ReturnValueTest.ReturnValueTestSchema(), required=True
        )

        class Meta:
            exclude = ("call_type",)  # don't serialize call_type

        @post_load
        def make(self, data, **kwargs):
            return RPCCondition(**data)

    def __repr__(self) -> str:
        r = f"{self.__class__.__name__}(function={self.method}, chain={self.chain})"
        return r

    def __init__(
        self,
        return_value_test: ReturnValueTest,
        condition_type: str = CONDITION_TYPE,
        name: Optional[str] = None,
        *args,
        **kwargs,
    ):
        # internal
        if condition_type != self.CONDITION_TYPE:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.CONDITION_TYPE} type."
            )

        try:
            self.rpc_call = self._create_rpc_call(*args, **kwargs)
        except ValueError as e:
            raise InvalidCondition(str(e))

        self.name = name
        self.condition_type = condition_type

        self.return_value_test = return_value_test  # output
        self._validate_expected_return_type()

    def _create_rpc_call(self, *args, **kwargs):
        return RPCCall(*args, **kwargs)

    @property
    def method(self):
        return self.rpc_call.method

    @property
    def chain(self):
        return self.rpc_call.chain

    @property
    def parameters(self):
        return self.rpc_call.parameters

    def _validate_expected_return_type(self):
        expected_return_type = RPCCall.ALLOWED_METHODS[self.method]
        comparator_value = self.return_value_test.value
        if is_context_variable(comparator_value):
            return

        if not isinstance(self.return_value_test.value, expected_return_type):
            raise InvalidCondition(
                f"Return value comparison for '{self.method}' call output "
                f"should be '{expected_return_type}' and not '{type(comparator_value)}'."
            )

    def _align_comparator_value_with_abi(
        self, return_value_test: ReturnValueTest
    ) -> ReturnValueTest:
        return return_value_test

    def verify(
        self, providers: Dict[int, Set[HTTPProvider]], **context
    ) -> Tuple[bool, Any]:
        """
        Verifies the onchain condition is met by performing a
        read operation and evaluating the return value test.
        """
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        return_value_test = self._align_comparator_value_with_abi(
            resolved_return_value_test
        )
        result = self.rpc_call.execute(providers=providers, **context)

        eval_result = return_value_test.eval(result)  # test
        return eval_result, result


class ContractCall(RPCCall):
    class Schema(RPCCall.Schema):
        contract_address = fields.Str(required=True)
        standard_contract_type = fields.Str(required=False)
        function_abi = fields.Dict(required=False)

        @post_load
        def make(self, data, **kwargs):
            return ContractCall(**data)

        @validates_schema
        def check_standard_contract_type_or_function_abi(self, data, **kwargs):
            standard_contract_type = data.get("standard_contract_type")
            function_abi = data.get("function_abi")
            try:
                _validate_contract_call_abi(
                    standard_contract_type, function_abi, method_name=data.get("method")
                )
            except ValueError as e:
                raise ValidationError(str(e))

    def __init__(
        self,
        method: str,
        contract_address: ChecksumAddress,
        call_type: str = "contract",
        standard_contract_type: Optional[str] = None,
        function_abi: Optional[ABIFunction] = None,
        *args,
        **kwargs,
    ):
        if not method:
            raise ValueError("Undefined method name")

        _validate_contract_call_abi(
            standard_contract_type, function_abi, method_name=method
        )

        # preprocessing
        contract_address = to_checksum_address(contract_address)
        self.contract_address = contract_address
        self.standard_contract_type = standard_contract_type
        self.function_abi = function_abi

        super().__init__(method=method, call_type=call_type, *args, **kwargs)
        self.contract_function = self._get_unbound_contract_function()

    def _validate_call_type(self, call_type):
        if call_type != "contract":
            raise ValueError(f"Invalid execution call type: {call_type}")

    def _validate_method(self, method):
        return method

    def _get_unbound_contract_function(self) -> ContractFunction:
        """Gets an unbound contract function to evaluate for this condition"""
        w3 = Web3()
        function_abi = _resolve_abi(
            w3=w3,
            standard_contract_type=self.standard_contract_type,
            method=self.method,
            function_abi=self.function_abi,
        )
        try:
            contract = w3.eth.contract(
                address=self.contract_address, abi=[function_abi]
            )
            contract_function = getattr(contract.functions, self.method)
            return contract_function
        except Exception as e:
            raise ValueError(
                f"Unable to find contract function, '{self.method}', for condition: {e}"
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
    CONDITION_TYPE = ConditionType.CONTRACT.value

    class Schema(RPCCondition.Schema, ContractCall.Schema):
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.CONTRACT.value), required=True
        )

        class Meta:
            exclude = ("call_type",)  # don't serialize call_type

        @post_load
        def make(self, data, **kwargs):
            return ContractCondition(**data)

    def __init__(
        self,
        condition_type: str = CONDITION_TYPE,
        *args,
        **kwargs,
    ):
        # call to super must be at the end for proper validation
        super().__init__(condition_type=condition_type, *args, **kwargs)

    def _create_rpc_call(self, *args, **kwargs) -> ContractCall:
        return ContractCall(*args, **kwargs)

    @property
    def function_abi(self):
        return self.rpc_call.function_abi

    @property
    def standard_contract_type(self):
        return self.rpc_call.standard_contract_type

    @property
    def contract_function(self):
        return self.rpc_call.contract_function

    @property
    def contract_address(self):
        return self.rpc_call.contract_address

    def _validate_expected_return_type(self) -> None:
        _validate_contract_function_expected_return_type(
            contract_function=self.contract_function,
            return_value_test=self.return_value_test,
        )

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
        return _align_comparator_value_with_abi(
            abi=self.contract_function.contract_abi[0],
            return_value_test=return_value_test,
        )


class SequentialContractCondition:
    CONDITION_TYPE = ConditionType.SEQUENTIAL_CONTRACTS.value

    MAX_NUM_CALLS = 5

    @classmethod
    def _validate_contract_calls(
        cls,
        contract_calls: List,
        exception_class: Union[Type[ValidationError], Type[InvalidCondition]],
    ):
        num_contract_calls = len(contract_calls)
        if num_contract_calls == 0:
            raise exception_class("Must be at least one contract call")

        if num_contract_calls > cls.MAX_NUM_CALLS:
            raise exception_class(
                f"Maximum of {cls.MAX_NUM_CALLS} contract calls are allowed"
            )

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.SEQUENTIAL_CONTRACTS.value),
            required=True,
        )
        contract_calls = fields.List(
            fields.Nested(ContractCall.Schema()), required=True
        )
        return_value_test = fields.Nested(
            ReturnValueTest.ReturnValueTestSchema(), required=True
        )

        # maintain field declaration ordering
        class Meta:
            ordered = True

        @validates_schema
        def validate_contract_calls(self, data, **kwargs):
            contract_calls = data["contract_calls"]
            SequentialContractCondition._validate_contract_calls(
                contract_calls, ValidationError
            )

        @post_load
        def make(self, data, **kwargs):
            return SequentialContractCondition(**data)

    def __init__(
        self,
        contract_calls: List[ContractCall],
        return_value_test: ReturnValueTest,
        condition_type: str = CONDITION_TYPE,
    ):
        # internal
        if condition_type != self.CONDITION_TYPE:
            raise InvalidCondition(
                f"{self.__class__.__name__} must be instantiated with the {self.CONDITION_TYPE} type."
            )

        self._validate_contract_calls(
            contract_calls=contract_calls, exception_class=InvalidCondition
        )

        self.contract_calls = contract_calls
        self.condition_type = condition_type
        self.return_value_test = return_value_test  # output

        final_contract_function = self.contract_calls[-1].contract_function
        _validate_contract_function_expected_return_type(
            contract_function=final_contract_function,
            return_value_test=self.return_value_test,
        )

    def __repr__(self):
        final_call = self.contract_calls[-1]
        r = f"{self.__class__.__name__}({len(self.contract_calls)} contract calls,  final_function={final_call.method} on chain={final_call.chain})"
        return r

    def verify(
        self, providers: Dict[int, Set[HTTPProvider]], **context
    ) -> Tuple[bool, Any]:
        resolved_return_value_test = self.return_value_test.with_resolved_context(
            **context
        )
        return_value_test = _align_comparator_value_with_abi(
            abi=self.contract_calls[-1].contract_function.contract_abi[0],
            return_value_test=resolved_return_value_test,
        )

        current_value = None
        for index, contract_call in enumerate(self.contract_calls):
            current_value = contract_call.execute(providers=providers, **context)
            context[f":multi_contract_condition_{index+1}_result"] = current_value

        final_result = current_value
        eval_result = return_value_test.eval(final_result)  # test
        return eval_result, final_result


def _validate_contract_function_expected_return_type(
    contract_function: ContractFunction, return_value_test: ReturnValueTest
) -> None:
    output_abi_types = _get_abi_types(contract_function.contract_abi[0])
    comparator_value = return_value_test.value
    comparator_index = return_value_test.index
    index_string = f"@index={comparator_index}" if comparator_index is not None else ""
    failure_message = (
        f"Invalid return value comparison type '{type(comparator_value)}' for "
        f"'{contract_function.fn_name}'{index_string} based on ABI types {output_abi_types}"
    )

    if len(output_abi_types) == 1:
        _validate_single_output_type(
            output_abi_types[0], comparator_value, comparator_index, failure_message
        )
    else:
        _validate_multiple_output_types(
            output_abi_types, comparator_value, comparator_index, failure_message
        )
