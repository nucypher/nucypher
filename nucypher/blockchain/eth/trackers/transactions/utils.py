from typing import Optional, Union

from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import PendingTx as PendingTxData
from web3.types import TxData, TxReceipt, Wei

from nucypher.utilities.logging import Logger

txtracker_log = Logger("tx.tracker")


def _get_average_blocktime(w3: Web3, sample_size: int) -> float:
    """Returns the average block time in seconds."""
    latest_block = w3.eth.get_block("latest")
    if latest_block.number == 0:
        return 0
    sample_block_number = latest_block.number - sample_size
    if sample_block_number <= 0:
        return 0
    base_block = w3.eth.get_block(sample_block_number)
    delta = latest_block.timestamp - base_block.timestamp
    average_block_time = delta / sample_size
    return average_block_time


def _log_gas_weather(base_fee: Wei, tip: Wei) -> None:
    base_fee_gwei = Web3.from_wei(base_fee, "gwei")
    tip_gwei = Web3.from_wei(tip, "gwei")
    txtracker_log.info(
        f"Gas conditions: base {base_fee_gwei} gwei | tip {tip_gwei} gwei"
    )


def _get_receipt(w3: Web3, data: Union[TxData, PendingTxData]) -> Optional[TxReceipt]:
    try:
        receipt = w3.eth.get_transaction_receipt(data["hash"])
    except TransactionNotFound:
        return
    status = receipt.get("status")
    if status == 0:
        # If status in response equals 1 the transaction was successful.
        # If it is equals 0 the transaction was reverted by EVM.
        # https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_transaction_receipt
        # TODO: What follow-up actions can be taken if the transaction was reverted?
        txtracker_log.info(
            f"Transaction {data['hash'].hex()} was reverted by EVM with status {status}"
        )
        return receipt
    return receipt
