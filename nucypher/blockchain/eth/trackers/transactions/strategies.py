from abc import ABC
from typing import Tuple

from web3 import Web3
from web3.types import Gwei, TxParams, Wei

from nucypher.blockchain.eth.trackers.transactions.exceptions import (
    Halt,
)
from nucypher.blockchain.eth.trackers.transactions.utils import (
    _log_gas_weather,
    txtracker_log,
)


class AsyncTxStrategy(ABC):
    """Abstract base class for transaction strategies."""

    _NAME = NotImplemented

    def __init__(self, w3: Web3):
        self.w3 = w3

    @property
    def name(self) -> str:
        """Used to identify the strategy in logs."""
        return self._NAME

    def execute(self, params: TxParams) -> TxParams:
        """
        Execute the strategy.

        Will be called by the transaction tracker when a
        transaction is ready to be retried. Accepts a TxParams
        dictionary containing transaction data from the most
        recent previous attempt.

        Must returns a new TxParams dictionary to use for the
        next attempt.
        """
        raise NotImplementedError


class SpeedupStrategy(AsyncTxStrategy):
    """Speedup strategy for pending transactions."""

    _NAME = "speedup"

    SPEEDUP_FACTOR = 1.125  # 12.5% increase
    MAX_TIP = Gwei(1)  # gwei maxPriorityFeePerGas per transaction

    def _calculate_speedup_fee(self, tx: TxParams) -> Tuple[Wei, Wei]:
        base_fee = self.w3.eth.get_block("latest")["baseFeePerGas"]
        suggested_tip = self.w3.eth.max_priority_fee
        _log_gas_weather(base_fee, suggested_tip)
        max_priority_fee = round(
            max(tx["maxPriorityFeePerGas"], suggested_tip) * self.SPEEDUP_FACTOR
        )
        max_fee_per_gas = round(
            max(
                tx["maxFeePerGas"] * self.SPEEDUP_FACTOR,
                (base_fee * 2) + max_priority_fee,
            )
        )
        return max_priority_fee, max_fee_per_gas

    def execute(self, params: TxParams) -> TxParams:
        old_tip, old_max_fee = params["maxPriorityFeePerGas"], params["maxFeePerGas"]
        new_tip, new_max_fee = self._calculate_speedup_fee(tx=params)
        tip_increase = round(Web3.from_wei(new_tip - old_tip, "gwei"), 4)
        fee_increase = round(Web3.from_wei(new_max_fee - old_max_fee, "gwei"), 4)

        if new_tip > self.MAX_TIP:
            raise Halt(
                f"Pending transaction maxPriorityFeePerGas exceeds spending cap {self.MAX_TIP}"
            )

        latest_nonce = self.w3.eth.get_transaction_count(params["from"], "latest")
        pending_nonce = self.w3.eth.get_transaction_count(params["from"], "pending")
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
