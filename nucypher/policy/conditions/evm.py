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

import re
from typing import Any, List, Optional, Tuple, Union

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from marshmallow import fields, post_load
from web3 import Web3
from web3.contract import ContractFunction
from web3.providers import BaseProvider

from nucypher.blockchain.eth.clients import PUBLIC_CHAINS
from nucypher.policy.conditions import STANDARD_ABIS
from nucypher.policy.conditions._utils import CamelCaseSchema
from nucypher.policy.conditions.base import ReencryptionCondition
from nucypher.policy.conditions.context import get_context_value, is_context_variable
from nucypher.policy.conditions.lingo import ReturnValueTest

# TODO: Move this method to a util function
__CHAINS = {
    60: 'ethereum',  # TODO: make a few edits for now
    131277322940537: 'testerchain',  # TODO: this one can be moved to a pytest fixture / setup logic
    **PUBLIC_CHAINS,
}


def _resolve_chain(chain: Union[str, int]) -> Tuple[str, int]:
    """Returns the name *and* chain ID given only a name *or* chain ID"""
    for pair in __CHAINS.items():
        if chain in pair:
            chain_id, chain_name = pair
            return chain_name, chain_id
    else:
        raise Exception(f'{chain} is not a known blockchain.')


def _resolve_abi(standard_contract_type: str, method: str, function_abi: List) -> List:
    """Resolves the contract an/or function ABI from a standard contract name"""
    if not (function_abi or standard_contract_type):
        # TODO: Is this protection needed?
        raise ValueError(f'Ambiguous ABI - Supply either an ABI or a standard contract name.')
    try:
        function_abi = STANDARD_ABIS[standard_contract_type]
    except KeyError:
        if not function_abi:
            raise Exception(f'No function ABI found')

    # TODO: Verify that the function and ABI pair match?
    # ABI(function_abi)
    return function_abi


def camel_case_to_snake(data: str) -> str:
    data = re.sub(r'(?<!^)(?=[A-Z])', '_', data).lower()
    return data


def _process_parameters(parameters, **context) -> List:
    """Handles request parameters"""
    processed_parameters = []
    for p in parameters:
        # TODO needs additional support for ERC1155 which has lists of values
        # context variables can only be strings, but other types of parameters can be passed
        if is_context_variable(p):
            p = get_context_value(context_variable=p, **context)
        processed_parameters.append(p)
    return processed_parameters


def _process_return_value_test(return_value_test, **context) -> ReturnValueTest:
    v = return_value_test.value
    if is_context_variable(v):
        v = get_context_value(context_variable=v, **context)
    return ReturnValueTest(return_value_test.comparator, value=v)


class RPCCondition(ReencryptionCondition):
    ALLOWED_METHODS = (  # TODO: Deny list instead of allow list, if any?

        # Contract
        'balanceOf',

        # RPC
        'eth_getBalance',
    )

    class Schema(CamelCaseSchema):
        name = fields.Str()
        chain = fields.Str()
        method = fields.Str()
        parameters = fields.List(fields.Field, attribute='parameters', required=False)
        return_value_test = fields.Nested(ReturnValueTest.ReturnValueTestSchema())

        @post_load
        def make(self, data, **kwargs):
            return RPCCondition(**data)

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__}(function={self.method}, chain={self.chain_name})'
        return r

    def __init__(self,
                 chain: str,
                 method: str,
                 return_value_test: ReturnValueTest,
                 parameters: Optional[List[str]] = None
                 ):

        # Validate input
        # _validate_parameters(parameters=parameters)
        # TODO: Additional validation (function is valid for ABI, RVT validity, standard contract name validity, etc.)

        # internal
        self.chain_name, self.chain_id = _resolve_chain(chain=chain)
        self.method = self.validate_method(method=method)

        # test
        self.parameters = parameters  # input
        self.return_value_test = return_value_test  # output

    @property
    def chain(self) -> str:
        return self.chain_name

    def validate_method(self, method):
        if method not in self.ALLOWED_METHODS:
            raise Exception(f'{method} is not a permitted RPC endpoint for conditions.')
        if not method.startswith('eth_'):
            raise Exception(f'Only eth RPC methods are accepted for conditions.')
        return method

    def _configure_provider(self, provider: BaseProvider):
        """Binds the condition's contract function to a blockchian provider for evaluation"""
        self.w3 = Web3(provider)
        provider_chain = self.w3.eth.chain_id
        if provider_chain != self.chain_id:
            raise Exception(f'This condition can only be evaluated on {self.chain_id} but the providers '
                            f'connection is to {provider_chain}')
        return provider

    def verify(self, provider: BaseProvider, *args, **contract_kwargs) -> Tuple[bool, Any]:
        """Performs onchain read and return value test"""
        self._configure_provider(provider=provider)
        parameters = _process_parameters(
            self.parameters, **contract_kwargs
        )  # resolve context variables
        return_value_test = _process_return_value_test(
            self.return_value_test, **contract_kwargs
        )  # resolve context variables
        rpc_endpoint_, rpc_method = self.method.split("_", 1)
        web3_py_method = camel_case_to_snake(rpc_method)
        rpc_function = getattr(self.w3.eth, web3_py_method)  # bind contract function (only exposes the eth API)
        rpc_result = rpc_function(*parameters)  # RPC read
        eval_result = return_value_test.eval(rpc_result)  # test
        return eval_result, rpc_result


class ContractCondition(RPCCondition):
    class Schema(RPCCondition.Schema):
        SKIP_VALUES = (None,)
        standard_contract_type = fields.Str(required=False)
        contract_address = fields.Str(required=True)
        function_abi = fields.Str(required=False)

        @post_load
        def make(self, data, **kwargs):
            return ContractCondition(**data)

    def __init__(self,
                 contract_address: ChecksumAddress,
                 standard_contract_type: str = None,
                 function_abi: List = None,
                 *args, **kwargs):
        # internal
        super().__init__(*args, **kwargs)
        self.w3 = Web3()  # used to instantiate contract function without a provider

        # preprocessing
        contract_address = to_checksum_address(contract_address)
        function_abi = _resolve_abi(
            standard_contract_type=standard_contract_type,
            method=self.method,
            function_abi=function_abi
        )

        # spec
        self.contract_address = contract_address
        self.standard_contract_type = standard_contract_type
        self.function_abi = function_abi
        self.contract_function = self._get_unbound_contract_function()

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__}(function={self.method}, ' \
            f'contract={self.contract_address[:6]}..., ' \
            f'chain={self.chain_name})'
        return r

    def validate_method(self, method):
        return method

    def _configure_provider(self, *args, **kwargs):
        super()._configure_provider(*args, **kwargs)
        self.contract_function.w3 = self.w3

    def _get_unbound_contract_function(self) -> ContractFunction:
        """Gets an unbound contract function to evaluate for this condition"""
        contract = self.w3.eth.contract(address=self.contract_address, abi=self.function_abi)
        contract_function = getattr(contract.functions, self.method)  # TODO: Use function selector instead/also?
        return contract_function

    def _evaluate(self, **contract_kwargs) -> Tuple[bool, Any]:
        """Performs onchain read and return value test"""
        parameters = _process_parameters(
            self.parameters, **contract_kwargs
        )  # resolve context variables
        return_value_test = _process_return_value_test(
            self.return_value_test, **contract_kwargs
        )  # resolve context variables
        bound_contract_function = self.contract_function(
            *parameters
        )  # bind contract function
        contract_result = bound_contract_function.call()  # onchain read
        eval_result = return_value_test.eval(contract_result)  # test
        return eval_result, contract_result

    def verify(self, provider: BaseProvider, **contract_kwargs) -> Tuple[bool, Any]:
        """Public API: Evaluate this condition using the given a blockchain provider and any supplied context kwargs"""
        self._configure_provider(provider=provider)
        result = self._evaluate(**contract_kwargs)
        return result
