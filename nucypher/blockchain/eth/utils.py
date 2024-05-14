import time
from decimal import Decimal
from typing import Dict, List, Union

import requests
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract.contract import ContractConstructor, ContractFunction
from web3.types import TxParams

from nucypher.blockchain.eth.constants import CHAINLIST_URL


def prettify_eth_amount(amount, original_denomination: str = 'wei') -> str:
    """
    Converts any ether `amount` in `original_denomination` and finds a suitable representation based on its length.
    The options in consideration are representing the amount in wei, gwei or ETH.
    :param amount: Input amount to prettify
    :param original_denomination: Denomination used by `amount` (by default, wei is assumed)
    :return: Shortest representation for `amount`, considering wei, gwei and ETH.
    """
    try:
        # First obtain canonical representation in wei. Works for int, float, Decimal and str amounts
        amount_in_wei = Web3.to_wei(Decimal(amount), original_denomination)

        common_denominations = ('wei', 'gwei', 'ether')

        options = [str(Web3.from_wei(amount_in_wei, d)) for d in common_denominations]

        best_option = min(zip(map(len, options), options, common_denominations))
        _length, pretty_amount, denomination = best_option

        if denomination == 'ether':
            denomination = 'ETH'
        pretty_amount += " " + denomination

    except Exception:  # Worst case scenario, we just print the str representation of amount
        pretty_amount = str(amount)

    return pretty_amount


def get_transaction_name(contract_function: Union[ContractFunction, ContractConstructor]) -> str:
    deployment = isinstance(contract_function, ContractConstructor)
    try:
        transaction_name = contract_function.fn_name.upper()
    except AttributeError:
        transaction_name = 'DEPLOY' if deployment else 'UNKNOWN'
    return transaction_name


def truncate_checksum_address(checksum_address: ChecksumAddress) -> str:
    return f"{checksum_address[:8]}...{checksum_address[-8:]}"


def get_tx_cost_data(transaction_dict: TxParams):
    try:
        # post-london fork transactions (Type 2)
        max_unit_price = transaction_dict["maxFeePerGas"]
        tx_type = "EIP-1559"
    except KeyError:
        # pre-london fork "legacy" transactions (Type 0)
        max_unit_price = transaction_dict["gasPrice"]
        tx_type = "Legacy"
    max_price_gwei = Web3.from_wei(max_unit_price, "gwei")
    max_cost_wei = max_unit_price * transaction_dict["gas"]
    max_cost = Web3.from_wei(max_cost_wei, "ether")
    return max_cost, max_price_gwei, tx_type


def rpc_endpoint_health_check(endpoint: str, max_drift_seconds: int = 60) -> bool:
    """
    Checks the health of an Ethereum RPC endpoint by comparing the timestamp of the latest block
    with the system time. The maximum drift allowed is `max_drift_seconds`.
    """
    query = {
        "jsonrpc": "2.0",
        "method": "eth_getBlockByNumber",
        "params": ["latest", False],
        "id": 1
    }
    try:
        response = requests.post(
            endpoint,
            json=query,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
    except requests.exceptions.RequestException:
        return False

    if response.status_code != 200:
        return False

    try:
        data = response.json()
        if "result" not in data:
            return False
    except requests.exceptions.RequestException:
        return False

    if data["result"] is None:
        return False
    block_data = data["result"]

    try:
        timestamp = int(block_data.get("timestamp"), 16)
    except TypeError:
        return False

    system_time = time.time()
    drift = abs(system_time - timestamp)
    if drift > max_drift_seconds:
        return False

    return True  # finally!


def get_default_rpc_endpoints() -> Dict[int, List[str]]:
    """
    Fetches the default RPC endpoints for various chains from the nucypher/chainlist repository.
    """
    # TODO: Memoize?  When to refresh?
    response = requests.get(CHAINLIST_URL)
    if response.status_code == 200:
        return {int(chain_id): endpoints for chain_id, endpoints in response.json().items()}
    else:
        # TODO: use an embedded fallback here?
        return {}


def get_healthy_default_rpc_endpoints(chain_id: int) -> List[str]:
    """
    Returns a list of healthy RPC endpoints for a given chain ID.
    """
    healthy = []
    endpoints = get_default_rpc_endpoints()
    chain_endpoints = endpoints.get(chain_id)
    if not chain_endpoints:
        return healthy
    for endpoint in chain_endpoints:
        if rpc_endpoint_health_check(endpoint=endpoint):
            healthy.append(endpoint)
    return healthy
