from typing import Any, Dict, List, Optional, Tuple

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from marshmallow import fields, post_load, validates_schema
from web3 import Web3
from web3.contract import ContractFunction
from web3.providers import BaseProvider
from web3.types import ABIFunction

from nucypher.policy.conditions import STANDARD_ABI_CONTRACT_TYPES, STANDARD_ABIS
from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.context import get_context_value, is_context_variable
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    NoConnectionToChain,
    RPCExecutionFailed,
)
from nucypher.policy.conditions.lingo import ReturnValueTest
from nucypher.policy.conditions.utils import CamelCaseSchema, camel_case_to_snake

# Permitted blockchains for condition evaluation
_CONDITION_CHAINS = (
    1,     # ethereum/mainnet
    5,     # ethereum/goerli
    137,   # polygon/mainnet
    80001  # polygon/mumbai
)


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
            function_abi = w3.eth.contract(abi=contract_abi).get_function_by_name(method).abi
        except ValueError as e:
            raise InvalidCondition(str(e))

    return ABIFunction(function_abi)


def _resolve_any_context_variables(
        parameters: List[Any], return_value_test: ReturnValueTest, **context
):
    processed_parameters = []
    for p in parameters:
        # TODO needs additional support for ERC1155 which has lists of values
        # context variables can only be strings, but other types of parameters can be passed
        if is_context_variable(p):
            p = get_context_value(context_variable=p, **context)
        processed_parameters.append(p)

    v = return_value_test.value
    if is_context_variable(v):
        v = get_context_value(context_variable=v, **context)
    k = return_value_test.key
    processed_return_value_test = ReturnValueTest(
        return_value_test.comparator, value=v, key=k
    )

    return processed_parameters, processed_return_value_test


def _validate_chain(chain: int) -> None:
    if not isinstance(chain, int):
        raise ValueError(f'"The chain" field of c a condition must be the '
                         f'integer of a chain ID (got "{chain}").')
    if chain not in _CONDITION_CHAINS:
        raise InvalidCondition(
            f"chain ID {chain} is not a permitted "
            f"blockchain for condition evaluation."
        )


class RPCCondition(ReencryptionCondition):
    ALLOWED_METHODS = (

        # Contract
        'balanceOf',

        # RPC
        'eth_getBalance',
    )  # TODO other allowed methods (tDEC #64)

    class Schema(CamelCaseSchema):
        SKIP_VALUES = (None,)
        name = fields.Str(required=False)
        chain = fields.Int(required=True)
        method = fields.Str(required=True)
        parameters = fields.List(fields.Field, attribute='parameters', required=False)
        return_value_test = fields.Nested(ReturnValueTest.ReturnValueTestSchema(), required=True)

        @post_load
        def make(self, data, **kwargs):
            return RPCCondition(**data)

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__}(function={self.method}, chain={self.chain})'
        return r

    def __init__(
        self,
        chain: int,
        method: str,
        return_value_test: ReturnValueTest,
        name: Optional[str] = None,
        parameters: Optional[List[Any]] = None,
    ):

        # Validate input
        # TODO: Additional validation (function is valid for ABI, RVT validity, standard contract name validity, etc.)
        _validate_chain(chain=chain)

        # internal
        self.name = name
        self.chain = chain
        self.method = self.validate_method(method=method)

        # test
        self.parameters = parameters  # input
        self.return_value_test = return_value_test  # output

    def validate_method(self, method):
        if method not in self.ALLOWED_METHODS:
            raise InvalidCondition(
                f"'{method}' is not a permitted RPC endpoint for condition evaluation."
            )
        if not method.startswith('eth_'):
            raise InvalidCondition(
                f"Only 'eth_' RPC methods are accepted for condition evaluation; '{method}' is not permitted."
            )
        return method

    def _configure_provider(self, providers: Dict[int, BaseProvider]):
        """Binds the condition's contract function to a blockchian provider for evaluation"""
        try:
            provider = providers[self.chain]
        except KeyError:
            raise NoConnectionToChain(chain=self.chain)

        # Instantiate a local web3 instance
        self.w3 = Web3(provider)

        # This next block validates that the actual web3 provider is *actually*
        # connected to the condition's chain ID by reading its RPC endpoint.
        provider_chain = self.w3.eth.chain_id
        if provider_chain != self.chain:
            raise InvalidCondition(
                f"This condition can only be evaluated on chain ID {self.chain} but the provider's "
                f"connection is to chain ID {provider_chain}"
            )
        return provider

    def _get_web3_py_function(self, rpc_method: str):
        web3_py_method = camel_case_to_snake(rpc_method)
        rpc_function = getattr(
            self.w3.eth, web3_py_method
        )  # bind contract function (only exposes the eth API)
        return rpc_function

    def _execute_call(self, parameters: List[Any]) -> Any:
        """Execute onchain read and return result."""
        rpc_endpoint_, rpc_method = self.method.split("_", 1)
        rpc_function = self._get_web3_py_function(rpc_method)
        rpc_result = rpc_function(*parameters)  # RPC read
        return rpc_result

    def verify(self, providers: Dict[int, BaseProvider], **context) -> Tuple[bool, Any]:
        """
        Verifies the onchain condition is met by performing a
        read operation and evaluating the return value test.
        """
        self._configure_provider(providers=providers)
        parameters, return_value_test = _resolve_any_context_variables(
            self.parameters, self.return_value_test, **context
        )
        try:
            result = self._execute_call(parameters=parameters)
        except Exception as e:
            raise RPCExecutionFailed(f"Contract call '{self.method}' failed: {e}")

        eval_result = return_value_test.eval(result)  # test
        return eval_result, result


class ContractCondition(RPCCondition):
    class Schema(RPCCondition.Schema):
        standard_contract_type = fields.Str(required=False)
        contract_address = fields.Str(required=True)
        function_abi = fields.Dict(required=False)

        @post_load
        def make(self, data, **kwargs):
            return ContractCondition(**data)

        @validates_schema
        def check_standard_contract_type_or_function_abi(self, data, **kwargs):
            standard_contract_type = data.get("standard_contract_type")
            function_abi = data.get("function_abi")
            if not (bool(standard_contract_type) ^ bool(function_abi)):
                raise InvalidCondition(
                    f"Provide 'standardContractType' or 'functionAbi'; got ({standard_contract_type}, {function_abi})."
                )

    def __init__(
        self,
        contract_address: ChecksumAddress,
        standard_contract_type: Optional[str] = None,
        function_abi: Optional[ABIFunction] = None,
        *args,
        **kwargs
    ):
        # internal
        super().__init__(*args, **kwargs)
        self.w3 = Web3()  # used to instantiate contract function without a provider

        if not (bool(standard_contract_type) ^ bool(function_abi)):
            raise InvalidCondition(
                f"Provide 'standard_contract_type' or 'function_abi'; got ({standard_contract_type}, {function_abi})."
            )

        # preprocessing
        contract_address = to_checksum_address(contract_address)

        # spec
        self.contract_address = contract_address
        self.standard_contract_type = standard_contract_type
        self.function_abi = function_abi
        self.contract_function = self._get_unbound_contract_function()

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__}(function={self.method}, ' \
            f'contract={self.contract_address[:6]}..., ' \
            f'chain={self.chain})'
        return r

    def validate_method(self, method):
        return method

    def _configure_provider(self, *args, **kwargs):
        super()._configure_provider(*args, **kwargs)
        self.contract_function.w3 = self.w3

    def _get_unbound_contract_function(self) -> ContractFunction:
        """Gets an unbound contract function to evaluate for this condition"""
        function_abi = _resolve_abi(
            w3=self.w3,
            standard_contract_type=self.standard_contract_type,
            method=self.method,
            function_abi=self.function_abi,
        )
        try:
            contract = self.w3.eth.contract(
                address=self.contract_address, abi=[function_abi]
            )
            contract_function = getattr(contract.functions, self.method)
            return contract_function
        except Exception as e:
            raise InvalidCondition(
                f"Unable to find contract function, '{self.method}', for condition: {e}"
            )

    def _execute_call(self, parameters: List[Any]) -> Any:
        """Execute onchain read and return result."""
        bound_contract_function = self.contract_function(
            *parameters
        )  # bind contract function
        contract_result = bound_contract_function.call()  # onchain read
        return contract_result
