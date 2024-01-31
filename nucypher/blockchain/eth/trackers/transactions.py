import json
import time
from json import JSONDecodeError
from tempfile import NamedTemporaryFile
from typing import Callable, Dict, List, Optional, Set, Tuple

from hexbytes import HexBytes
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.exceptions import TransactionNotFound
from web3.types import Nonce

from nucypher.utilities.task import SimpleTask


class TransactionTracker(SimpleTask):
    INTERVAL = 10
    BLOCK_INTERVAL = 20  # ~20 blocks
    BLOCK_SAMPLE_SIZE = 100_000  # blocks
    DEFAULT_MAX_TIP = 10  # gwei maxPriorityFeePerGas per transaction
    DEFAULT_TIMEOUT = (60 * 60) * 1  # 1 hour
    RPC_THROTTLE = 0.5  # seconds between RPC calls

    class TransactionFinalized(Exception):
        pass

    class SpendingCapExceeded(Exception):
        pass

    def __init__(
        self,
        w3: Web3,
        transacting_power: "actors.TransactingPower",
        max_tip: int = DEFAULT_MAX_TIP,
        timeout: int = DEFAULT_TIMEOUT,
        tracking_hook: Callable = None,
        finalize_hook: Callable = None,
        *args,
        **kwargs,
    ):
        self.w3 = w3
        self.transacting_power = transacting_power  # TODO: Use LocalAccount instead
        self.address = transacting_power.account

        self.max_tip = self.w3.to_wei(max_tip, "gwei")
        self.timeout = timeout

        self.__tracking_hook = tracking_hook
        self.__finalize_hook = finalize_hook

        self.__seen = dict()
        self.__txs: Dict[int, str] = dict()
        self.__file = NamedTemporaryFile(
            mode="w+",
            delete=False,
            encoding="utf-8",
            prefix="txs-cache-",
            suffix=".json",
        )
        super().__init__(*args, **kwargs)

    def __write_file(self):
        self.__file.seek(0)
        self.__file.truncate()
        json.dump(self.__txs, self.__file)
        self.__file.flush()
        self.log.debug(f"Updated transaction cache file {self.__file.name}")

    def __read_file(self) -> Dict[int, HexBytes]:
        self.__file.seek(0)
        try:
            txs = json.load(self.__file)
        except JSONDecodeError:
            txs = dict()
        self.log.debug(f"Loaded transaction cache file {self.__file.name}")
        txs = dict((int(nonce), HexBytes(txhash)) for nonce, txhash in txs.items())
        return txs

    def __track(self, nonce: int, txhash: HexBytes) -> None:
        if nonce in self.__txs:
            replace, old = True, self.__txs[nonce]
            self.log.warn(f"Replacing tracking txhash #{nonce}|{old} -> {txhash.hex()}")
        else:
            self.log.info(f"Started tracking transaction #{nonce}|{txhash.hex()}")
            self.__seen[nonce] = time.time()
        self.__txs[int(nonce)] = txhash.hex()

    def __untrack(self, nonce: int) -> None:
        removed_txhash = self.__txs.pop(nonce, None)
        self.__seen.pop(nonce, None)
        if removed_txhash is None:
            raise ValueError(f"Transaction #{nonce} not found")
        self.log.info(f"Stopped tracking transaction #{nonce}")

    def track(self, txs: Set[Tuple[int, HexBytes]]) -> None:
        for nonce, txhash in txs:
            self.__track(nonce=nonce, txhash=txhash)
        self.__write_file()
        if self.__tracking_hook:
            self.__tracking_hook(txs=txs)

    def untrack(self, nonces: Set[int]) -> None:
        for nonce in nonces:
            self.__untrack(nonce=nonce)
        self.__write_file()
        if self.__finalize_hook:
            self.__finalize_hook(nonces=nonces)

    def is_tracked(self, nonce: int = None, txhash: HexBytes = None) -> bool:
        tracked = dict(self.tracked)
        if nonce:
            return int(nonce) in tracked
        elif txhash:
            return txhash in tracked.values()
        return False

    @property
    def tracked(self) -> List[Tuple[Nonce, HexBytes]]:
        return [
            (Nonce(int(nonce)), HexBytes(txhash))
            for nonce, txhash in self.__txs.items()
        ]

    def get_txhash(self, nonce: int) -> Optional[HexBytes]:
        return HexBytes(self.__txs.get(nonce))

    def __is_tx_finalized(self, tx: AttributeDict, txhash: HexBytes) -> bool:
        if tx.blockHash is None:
            return False
        try:
            receipt = self.w3.eth.get_transaction_receipt(txhash)
        except TransactionNotFound:
            return False
        status = receipt.get("status")
        if status == 0:
            # If status in response equals 1 the transaction was successful.
            # If it is equals 0 the transaction was reverted by EVM.
            # https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_transaction_receipt
            # TODO: What follow-up actions can be taken if the transaction was reverted?
            self.log.info(
                f"Transaction {txhash.hex()} was reverted by EVM with status {status}"
            )
        self.log.info(
            f"Transaction {txhash.hex()} has been included in block #{tx.blockNumber}"
        )
        return True

    def _calculate_speedup_fee(self, tx: AttributeDict) -> Tuple[int, int]:
        # Fetch the current base fee and priority fee
        base_fee = self.w3.eth.get_block("latest")["baseFeePerGas"]
        tip = self.w3.eth.max_priority_fee
        self._log_gas_weather(base_fee, tip)
        factor = 1.2
        increased_tip = round(max(tx.maxPriorityFeePerGas, tip) * factor)

        fee_per_gas = round(
            max(tx.maxFeePerGas * factor, (base_fee * 2) + increased_tip)
        )
        return increased_tip, fee_per_gas

    def _get_average_blocktime(self) -> float:
        """Returns the average block time in seconds."""
        latest_block = self.w3.eth.get_block("latest")
        if latest_block.number == 0:
            return 0
        sample_block_number = latest_block.number - self.BLOCK_SAMPLE_SIZE
        if sample_block_number <= 0:
            return 0
        base_block = self.w3.eth.get_block(sample_block_number)
        average_block_time = (
            latest_block.timestamp - base_block.timestamp
        ) / self.BLOCK_SAMPLE_SIZE
        return average_block_time

    def _log_gas_weather(self, base_fee: int, tip: int) -> None:
        base_fee_gwei = self.w3.from_wei(base_fee, "gwei")
        tip_gwei = self.w3.from_wei(tip, "gwei")
        self.log.info(
            "Current gas conditions: "
            f"base fee {base_fee_gwei} gwei | "
            f"tip {tip_gwei} gwei"
        )

    @staticmethod
    def _prepare_transaction(tx: AttributeDict) -> AttributeDict:
        """
        Filter out fields that are not needed for signing
        TODO: is there a better way to do this?
        """
        final_fields = {
            "blockHash",
            "blockNumber",
            "transactionIndex",
            "yParity",
            "input",
            "gasPrice",
            "hash",
        }
        tx = dict(tx)
        for key in final_fields:
            tx.pop(key, None)
        tx = AttributeDict(tx)
        return tx

    def _make_speedup_transaction(self, tx: AttributeDict) -> AttributeDict:
        tip, max_fee = self._calculate_speedup_fee(tx)
        tx = self._prepare_transaction(tx)
        tx = dict(tx)  # allow mutation
        tx["maxPriorityFeePerGas"] = tip
        tx["maxFeePerGas"] = max_fee
        tx = AttributeDict(tx)  # disallow mutation
        return tx

    def _calculate_cancel_fee(self, factor: int = 2) -> Tuple[int, int]:
        base_fee = self.w3.eth.get_block("latest")["baseFeePerGas"]
        tip = self.w3.eth.max_priority_fee * factor
        max_fee = (base_fee * 2) + tip
        return tip, max_fee

    def _make_cancellation_transaction(
        self, chain_id: int, nonce: int
    ) -> AttributeDict:
        tip, max_fee = self._calculate_cancel_fee()
        tx = AttributeDict(
            {
                "type": "0x2",
                "nonce": nonce,
                "to": self.transacting_power.account,
                "value": 0,
                "gas": 21000,
                "maxPriorityFeePerGas": tip,
                "maxFeePerGas": max_fee,
                "chainId": chain_id,
                "from": self.transacting_power.account,
            }
        )
        return tx

    def _handle_transaction_error(self, e: Exception, tx: AttributeDict) -> None:
        rpc_response = e.args[0]
        self.log.critical(
            f"Transaction #{tx.nonce} | {tx.hash.hex()} "
            f"failed with { rpc_response['code']} | "
            f"{rpc_response['message']}"
        )

    def _sign_and_send(self, tx: AttributeDict) -> HexBytes:
        tx = self._prepare_transaction(tx)
        signed_tx = self.transacting_power.sign_transaction(tx)
        try:
            txhash = self.w3.eth.send_raw_transaction(signed_tx)
        except ValueError as e:
            self._handle_transaction_error(e, tx=tx)
        else:
            self.log.info(
                f"Broadcasted transaction #{tx.nonce} | txhash {txhash.hex()}"
            )
            return txhash

    def speedup_transaction(self, txhash: HexBytes) -> HexBytes:
        tx = self.w3.eth.get_transaction(txhash)
        finalized = self.__is_tx_finalized(tx=tx, txhash=txhash)
        if finalized:
            raise self.TransactionFinalized
        if tx.maxPriorityFeePerGas > self.max_tip:
            raise self.SpendingCapExceeded
        tx = self._make_speedup_transaction(tx)
        tip, base_fee = tx.maxPriorityFeePerGas, tx.maxFeePerGas
        self._log_gas_weather(base_fee, tip)
        self.log.info(
            f"Speeding up transaction #{tx.nonce} with "
            f"maxPriorityFeePerGas={tip} and maxFeePerGas={base_fee}"
        )
        txhash = self._sign_and_send(tx)
        return txhash

    def cancel_transaction(self, nonce: int) -> HexBytes:
        tx = self._make_cancellation_transaction(
            nonce=nonce, chain_id=self.w3.eth.chain_id
        )
        tx = self._prepare_transaction(tx)
        self.log.info(
            f"Cancelling transaction #{nonce} with "
            f"tip: {tx.maxPriorityFeePerGas} and fee: {tx.maxFeePerGas}"
        )
        txhash = self._sign_and_send(tx)
        return txhash

    def cancel_transactions(self, nonces: Set[int]) -> None:
        self.log.info(f"Cancelling {len(nonces)} transactions")
        txs = set()
        for nonce in nonces:
            txhash = self.cancel_transaction(nonce=nonce)
            txs.add((nonce, txhash))
            time.sleep(self.RPC_THROTTLE)
        self.track(txs=txs)

    def start(self, now: bool = False):
        self.log.info("Starting Transaction Tracker")
        pending_nonce = self.w3.eth.get_transaction_count(self.address, "pending")
        latest_nonce = self.w3.eth.get_transaction_count(self.address, "latest")
        pending = pending_nonce - latest_nonce
        pending_nonces = set(range(latest_nonce, pending_nonce))
        self.log.info(
            f"Detected {pending} pending transactions "
            f"with nonces {', '.join(map(str, pending_nonces))}"
        )

        self._restore_state(pending_nonces)
        self._handle_untracked_transactions(pending_nonces)

        average_block_time = self._get_average_blocktime()
        self._task.interval = round(average_block_time * self.BLOCK_INTERVAL)
        self.log.info(
            f"Average block time is {average_block_time} seconds \n"
            f"Set tracking interval to {self._task.interval} seconds \n"
            f"Transaction speedups spending cap is {self.max_tip} wei per transaction"
        )

        super().start(now=now)

    def _handle_untracked_transactions(self, pending_nonces: Set[int]) -> None:
        untracked_nonces = set(
            filter(lambda n: not self.is_tracked(nonce=n), pending_nonces)
        )
        if len(untracked_nonces) > 0:
            # Cancels all pending transactions that are not tracked
            self.log.warn(
                f"Detected {len(untracked_nonces)} untracked "
                f"pending transactions with nonces {', '.join(map(str, untracked_nonces))}"
            )
            self.cancel_transactions(nonces=untracked_nonces)

    def _restore_state(self, pending_nonces) -> None:
        """Read the pending transaction data from the disk"""
        records = self.__read_file()
        if len(records) > 0:
            disk_txhashes = "\n".join(
                f"#{nonce}|{txhash.hex()}" for nonce, txhash in records.items()
            )
            self.log.debug(
                f"Loaded {len(records)} tracked txhashes "
                f"with nonces {', '.join(map(str, records.keys()))} "
                f"from disk\n{disk_txhashes}"
            )
        if not pending_nonces:
            self.log.info("No pending transactions to track")
        elif set(records) == set(pending_nonces):
            self.log.info("All cached transactions are tracked")
        else:
            diff = set(pending_nonces) - set(records)
            self.log.warn("Untracked nonces: {}".format(", ".join(map(str, diff))))
        self.track(txs=set(records.items()))

    def __is_timed_out(self, nonce: int) -> bool:
        created = self.__seen.get(nonce)
        if not created:
            return False
        timeout = (time.time() - created) > self.timeout
        return timeout

    def is_timed_out(self, nonce: int) -> bool:
        timeout = self.__is_timed_out(nonce=nonce)
        if timeout:
            self.log.warn(
                f"Transaction #{nonce} has been pending for more than"
                f"{self.timeout} seconds"
            )
            return True
        self.log.info(
            f"Transaction #{nonce} has been pending for"
            f" {time.time() - self.__seen[nonce]} seconds"
        )
        time_remaining = round(self.timeout - (time.time() - self.__seen[nonce]))
        self.log.info(f"Transaction #{nonce} will timeout in {time_remaining} seconds")
        return False

    def run(self):
        if len(self.tracked) == 0:
            self.log.info(
                f"Steady as she goes... next cycle in {self.INTERVAL} seconds"
            )
            return False
        self.log.info(
            f"Tracking {len(self.tracked)} transaction{'s' if len(self.tracked) > 1 else ''}"
        )

        replacements, removals = set(), set()
        for nonce, txhash in self.tracked:
            # NOTE: do not mutate __txs while iterating over it.
            if self.is_timed_out(nonce=nonce):
                removals.add(nonce)
                continue
            try:
                replacement_txhash = self.speedup_transaction(txhash)
            except self.TransactionFinalized:
                removals.add(nonce)
                continue
            except self.SpendingCapExceeded:
                self.log.warn(
                    f"Transaction #{nonce} exceeds spending cap {self.max_tip} wei"
                )
                continue
            except TransactionNotFound:
                removals.add((nonce, txhash))
                self.log.info(f"Transaction #{nonce}|{txhash.hex()} not found")
                continue
            else:
                # engage throttle when sending multiple transactions
                replacements.add((nonce, replacement_txhash))
                time.sleep(self.RPC_THROTTLE)

        # Update the cache
        self.track(txs=replacements)
        self.untrack(nonces=removals)

        if replacements:
            self.log.info(f"Replaced {len(replacements)} transactions")
        if removals:
            self.log.info(f"Untracked {len(removals)} transactions")

    def handle_errors(self, *args, **kwargs):
        self.log.warn("Error during transaction: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting transaction task!")
            self.start(now=False)  # take a breather
