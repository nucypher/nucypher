from typing import Any, Dict, List

from multicall import Call, Multicall
from web3 import Web3
from web3.providers import BaseProvider
from web3.types import ABIFunction

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.exceptions import InvalidCondition, NoConnectionToChain


# Transforms function ABI to signature format supported by multicall.py:
# <func_name>(input_type1,input_type2)(output_type1,output_type2)
def abi_to_signature(abi: ABIFunction) -> str:
    signature = abi["name"]
    signature += "("
    for input in abi["inputs"]:
        signature += input["type"] + ","
    signature = signature[:-1]
    signature += ")("
    for output in abi["outputs"]:
        signature += output["type"] + ","
    signature = signature[:-1]
    signature += ")"

    return signature


class MulticallConditions:
    def __init__(
        self,
        conditions: List[AccessControlCondition],
        providers: Dict[int, BaseProvider],
        context: Dict[str, Any],
    ) -> None:
        filtered_conditions = filter(self._filter, conditions)
        chain_conditions = {}

        # TODO: make a new test for *multi-chain* compound condition case
        for condition in filtered_conditions:
            if condition.chain in chain_conditions:
                chain_conditions[condition.chain].append(condition)
            else:
                chain_conditions[condition.chain] = [condition]

        multicalls = {}
        for chain in chain_conditions:
            w3 = self._get_w3(providers, chain)

            calls = []
            for condition in chain_conditions[chain]:
                calls.append(self._build_call(condition, context))
            multicalls[chain] = Multicall(w3, calls)

        self.multicalls = multicalls

    def _get_w3(self, providers: Dict[int, BaseProvider], chain: int) -> Web3:
        try:
            provider = providers[chain]
        except KeyError:
            raise NoConnectionToChain(chain=self.chain)

        w3 = Web3(provider)

        # This next block validates that the actual web3 provider is *actually*
        # connected to the condition's chain ID by reading its RPC endpoint.
        provider_chain = w3.eth.chain_id
        if provider_chain != chain:
            raise InvalidCondition(
                f"This condition can only be evaluated on chain ID {chain} but the provider's "
                f"connection is to chain ID {provider_chain}"
            )
        return w3

    # Only returns conditions that are supported by multicall contract
    def _filter(self, condition: AccessControlCondition) -> bool:
        # TODO: this only filters conditions, not operands
        # TODO: this only filters contract conditions, not RPC or blocktime
        return condition.__class__.__name__ in [
            "ContractCondition",
            "RPCCondition",
            "TimeCondition",
        ]

    # TODO: add RPCCondition and TimeCondition
    # TODO: create a separate module or class with the supported contract calls
    # TODO:     (balanceOf, NFTOwnership, RPC calls, time-based conditions...)
    def _build_call(
        self, condition: AccessControlCondition, context: Dict[str, Any]
    ) -> Call:
        if condition.__class__.__name__ == "ContractCondition":
            signature = abi_to_signature(
                ABIFunction(condition.contract_function.contract_abi[0])
            )

    def verify(self) -> Dict[int, Dict[str, Any]]:
        multicall_results = {}
        for chain in self.multicalls:
            multicall_results[chain] = self.multicalls[chain]()
        return multicall_results
