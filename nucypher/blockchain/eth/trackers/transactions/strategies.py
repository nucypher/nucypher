from typing import Tuple

from web3 import Web3
from web3.types import TxParams, Wei

from nucypher.blockchain.eth.trackers.transactions.utils import (
    _log_gas_weather,
    txtracker_log,
)

SPEEDUP_FACTOR = 1.125  # 12.5% increase


def _calculate_speedup_fee(w3: Web3, tx: TxParams) -> Tuple[Wei, Wei]:
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    suggested_tip = w3.eth.max_priority_fee
    _log_gas_weather(base_fee, suggested_tip)
    max_priority_fee = round(
        max(tx["maxPriorityFeePerGas"], suggested_tip) * SPEEDUP_FACTOR
    )
    max_fee_per_gas = round(
        max(tx["maxFeePerGas"] * SPEEDUP_FACTOR, (base_fee * 2) + max_priority_fee)
    )
    return max_priority_fee, max_fee_per_gas


def _make_speedup_params(w3: Web3, params: TxParams) -> TxParams:
    old_tip, old_max_fee = params["maxPriorityFeePerGas"], params["maxFeePerGas"]
    new_tip, new_max_fee = _calculate_speedup_fee(w3=w3, tx=params)
    tip_increase = round(Web3.from_wei(new_tip - old_tip, "gwei"), 4)
    fee_increase = round(Web3.from_wei(new_max_fee - old_max_fee, "gwei"), 4)

    latest_nonce = w3.eth.get_transaction_count(params["from"], "latest")
    pending_nonce = w3.eth.get_transaction_count(params["from"], "pending")
    if pending_nonce - latest_nonce > 0:
        txtracker_log.warn("Overriding pending transaction!")

    txtracker_log.info(
        f"Speeding up transaction #{params['nonce']} \n"
        f"maxPriorityFeePerGas (~+{tip_increase} gwei) {old_tip} -> {new_tip} \n"
        f"maxFeePerGas (~+{fee_increase} gwei) {old_max_fee} -> {new_max_fee}"
    )
    params = dict(params)
    params["maxPriorityFeePerGas"] = new_tip
    params["maxFeePerGas"] = new_max_fee
    params["nonce"] = latest_nonce
    params = TxParams(params)
    return params
