import json
import time
from collections import deque
from json import JSONDecodeError
from tempfile import NamedTemporaryFile
from typing import Dict, Optional, Tuple, Union, List

from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import Nonce, Wei, Gwei, TxData, TxParams, RPCError, PendingTx

from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask

TxHash = HexBytes

log = Logger('txtracker')


def _get_average_blocktime(w3, sample_size: int) -> float:
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


def _calculate_speedup_fee(w3: Web3, tx: TxParams, factor: float) -> Tuple[Wei, Wei]:
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    suggested_tip = w3.eth.max_priority_fee
    _log_gas_weather(base_fee, suggested_tip)
    max_priority_fee = round(
        max(tx["maxPriorityFeePerGas"], suggested_tip) * factor
    )
    max_fee_per_gas = round(
        max(tx["maxFeePerGas"] * factor, (base_fee * 2) + max_priority_fee)
    )
    return max_priority_fee, max_fee_per_gas


def _log_gas_weather(base_fee: Wei, tip: Wei) -> None:
    base_fee_gwei = Web3.from_wei(base_fee, "gwei")
    tip_gwei = Web3.from_wei(tip, "gwei")
    log.info(f"Gas conditions: base {base_fee_gwei} gwei | tip {tip_gwei} gwei")


def _is_tx_finalized(w3: Web3, data: Union[TxData, PendingTx]) -> bool:
    # if not data.get('blockHash'):
    #     return False
    try:
        receipt = w3.eth.get_transaction_receipt(data["hash"])
    except TransactionNotFound:
        return False
    status = receipt.get("status")
    if status == 0:
        # If status in response equals 1 the transaction was successful.
        # If it is equals 0 the transaction was reverted by EVM.
        # https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_transaction_receipt
        # TODO: What follow-up actions can be taken if the transaction was reverted?
        log.info(
            f"Transaction {data['hash'].hex()} was reverted by EVM with status {status}"
        )
    log.info(
        f"[success] Transaction #{data['nonce']}|{data['hash'].hex()} "
        f"has been included in block #{data['blockNumber']}"
    )
    return True


def _make_tx_params(tx: TxData) -> TxParams:
    if tx.get("gasPrice"):
        # TODO: legacy transaction
        raise NotImplementedError("Only EIP-1559 transactions are supported")

    return TxParams(
        {
            "nonce": tx['nonce'],
            "maxPriorityFeePerGas": tx["maxPriorityFeePerGas"],
            "maxFeePerGas": tx["maxFeePerGas"],
            "chainId": tx["chainId"],
            "gas": tx["gas"],
            "type": "0x2",
            "from": tx["from"],
            "to": tx["to"],
            "value": tx["value"],
            "data": tx.get("data", b"")
        }
    )


def _make_speedup_params(w3: Web3, tx: TxParams, factor: float) -> TxParams:
    old_tip, old_max_fee = tx["maxPriorityFeePerGas"], tx["maxFeePerGas"]
    new_tip, new_max_fee = _calculate_speedup_fee(w3=w3, tx=tx, factor=factor)
    tip_increase = round(Web3.from_wei(new_tip - old_tip, 'gwei'), 4)
    fee_increase = round(Web3.from_wei(new_max_fee - old_max_fee, 'gwei'), 4)
    nonce = w3.eth.get_transaction_count(tx["from"], "latest")
    log.info(
        f"Speeding up transaction #{tx['nonce']} \n"
        f"maxPriorityFeePerGas (~+{tip_increase} gwei) {old_tip} -> {new_tip} \n"
        f"maxFeePerGas (~+{fee_increase} gwei) {old_max_fee} -> {new_max_fee}"
    )
    tx["maxPriorityFeePerGas"] = new_tip
    tx["maxFeePerGas"] = new_max_fee
    tx["nonce"] = nonce
    tx = TxParams(tx)
    return tx


def _handle_transaction_error(e: Exception, tx: TxParams) -> None:
    error = RPCError(**e.args[0])
    log.critical(
        f"Transaction #{tx['nonce']} failed with {error['code']} | {error['message']}"
    )
    if error['code'] == -32000:
        if "insufficient funds" in error['message']:
            raise TransactionTracker.InsufficientFunds


class TransactionTracker(SimpleTask):
    INTERVAL = 60 * 5  # 5 min. steady state interval
    BLOCK_INTERVAL = 20  # ~20 blocks
    BLOCK_SAMPLE_SIZE = 1_000  # blocks
    DEFAULT_MAX_TIP = Gwei(10)  # gwei maxPriorityFeePerGas per transaction
    DEFAULT_TIMEOUT = 60 * 60  # 1 hour
    RPC_THROTTLE = 1  # seconds between RPC calls
    SPEEDUP_FACTOR = 1.125  # 12.5% increase

    class TransactionFinalized(Exception):
        """raised when a transaction has been included in a block"""

    class SpendingCap(Exception):
        """raised when a transaction exceeds the spending cap"""

    class InsufficientFunds(RPCError):
        """raised when a transaction exceeds the spending cap"""

    def __init__(
            self,
            w3: Web3,
            transacting_power: "actors.TransactingPower",
            max_tip: Gwei = DEFAULT_MAX_TIP,
            timeout: int = DEFAULT_TIMEOUT,
            *args, **kwargs,
    ):
        # w3
        self.w3 = w3
        self.transacting_power = transacting_power  # TODO: Use LocalAccount instead
        self.address = transacting_power.account

        # gwei -> wei
        self.max_tip: Wei = self.w3.to_wei(max_tip, "gwei")
        self.timeout = timeout

        # state
        self.__queue = deque()
        self.__pending: Optional[Tuple[Nonce, TxHash]] = None
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
        pending = dict()
        if self.__pending:
            pending = {str(self.__pending[0]): self.__pending[1].hex()}
        json.dump({
            'pending': pending,
            'queue': self.__serialize_queue()
        }, self.__file)
        self.__file.flush()
        self.log.debug(f"Updated transaction cache file {self.__file.name}")

    def __restore_state(self) -> None:
        self.__file.seek(0)
        try:
            data = json.load(self.__file)
        except JSONDecodeError:
            data = dict()
        self.log.debug(f"Loaded {len(data)} transactions from cache file {self.__file.name}")
        pending = data.get('pending', dict())
        txs = data.get('queue', list())
        self.__queue = deque(txs)
        self.__pending = tuple(pending.items())

    def __serialize_queue(self) -> List:
        queue = []
        for tx in self.__queue:
            tx = {str(k): v for k, v in tx.items()}
            queue.append(tx)
        return queue

    def __clear_pending(self) -> None:
        self.__pending = None
        self.__write_file()

    @property
    def idle(self) -> bool:
        return (not self.__pending) and len(self.__queue) == 0

    def __track_pending_txhash(self, txhash: TxHash) -> None:
        self.log.info(f"Tacking pending transaction {txhash.hex()}")
        self.__pending = (time.time(), txhash)

    def handle_errors(self, *args, **kwargs):
        self.log.warn("Error during transaction: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting transaction task!")
            self.start(now=False)  # take a breather

    def __sign_and_send(self, tx: TxParams) -> PendingTx:
        try:
            txhash = self.w3.eth.send_raw_transaction(
                self.transacting_power.sign_transaction(tx)
            )
        except ValueError as e:
            _handle_transaction_error(e, tx=tx)
            raise e
        tx["hash"] = txhash
        return PendingTx(tx)

    def __is_timed_out(self) -> bool:
        if not self.__pending:
            return False
        created, _ = self.__pending
        timeout = (time.time() - created) > self.timeout
        return timeout

    def is_timed_out(self) -> bool:
        timeout = self.__is_timed_out()
        created, txhash = self.__pending
        if timeout:
            self.log.warn(
                f"[timeout] Transaction {txhash.hex()} has been pending for more than"
                f"{self.timeout} seconds"
            )
            return True
        time_remaining = round(self.timeout - (time.time() - created))
        minutes = round(time_remaining / 60)
        remainder_seconds = time_remaining % 60
        end_time = time.time() + time_remaining
        human_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        if time_remaining < (60 * 2):
            self.log.warn(
                f"Transaction {txhash.hex()} will timeout in "
                f"{minutes}m{remainder_seconds}s at {human_end_time}"
            )
        else:
            self.log.info(
                f"Pending Transaction: {txhash.hex()} \n"
                f"Elapsed {round(time.time() - created)}s, "
                f"Remaining {minutes}m{remainder_seconds}s, "
                f"Timeout {human_end_time}"
            )
        return False

    def __fire(self, tx: PendingTx) -> Tuple[bool, bool]:
        success, removal, final = False, False, False
        try:
            replacement = self.__sign_and_send(tx=tx)
        except self.TransactionFinalized:
            final = True
        except self.SpendingCap:
            self.log.warn(
                f"Transaction {tx['hash'].hex()} exceeds spending cap {self.max_tip} wei"
            )
        except TransactionNotFound:
            removal = True
            self.log.info(f"Transaction {tx['hash'].hex()} not found")
        else:
            success = True
            self.__track_pending_txhash(txhash=replacement["hash"])
            self.log.info(
                f"[retry] Sped up transaction #{replacement['nonce']}|{replacement['hash'].hex()}"
            )
        if removal or final:
            self.__clear_pending()
        return success, final

    #######
    # API #
    #######

    def queue_transaction(self, tx: TxParams) -> None:
        self.__queue.append(tx)
        self.log.info(f"Queued transaction #{tx['nonce']} "
                      f"in broadcast queue position {len(self.__queue)}")
        self.__write_file()

    def speedup(self) -> Tuple[bool, bool]:
        if not self.__pending:
            raise ValueError("No pending transaction to speedup")

        created, txhash = self.__pending
        if self.is_timed_out():
            self.__clear_pending()
            return False, False

        data = self.w3.eth.get_transaction(txhash)
        if _is_tx_finalized(w3=self.w3, data=data):
            self.__clear_pending()
            return True, True

        if data["maxPriorityFeePerGas"] > self.max_tip:
            raise self.SpendingCap

        tx = _make_speedup_params(
            tx=data,
            w3=self.w3,
            factor=self.SPEEDUP_FACTOR
        )

        success, final = self.__fire(tx=tx)
        return success, final

    def broadcast(self) -> Tuple[bool, bool]:
        tx = self.__queue.popleft()
        tx = _make_tx_params(tx)
        success, final = self.__fire(tx=tx)
        if not success:
            self.__queue.append(tx)
        return success, final

    def start(self, now: bool = False) -> None:
        self.__restore_state()
        super().start(now=now)
        self.log.info("Starting transaction tracker")
        self.self_test()

    def run(self):
        if self.idle:
            self.log.info(f"[idle] cycle interval is {self._task.interval} seconds")
            return
        self.log.info(
            f"Tracking {len(self.__queue)} queued transaction{'s' if len(self.__queue) > 1 else ''} "
            f"{'and 1 pending transaction' if self.__pending else ''}"
        )

        average_block_time = _get_average_blocktime(w3=self.w3, sample_size=self.BLOCK_SAMPLE_SIZE)
        self._task.interval = round(average_block_time * self.BLOCK_INTERVAL)
        self.log.info(f"[working] cycle interval is {self._task.interval} seconds")

        if self.__pending:
            self.speedup()
        if len(self.__queue) > 0 and not self.__pending:
            self.broadcast()
        if self.idle:
            self._task.interval = self.INTERVAL
            self.log.info(f"[done] returning to idle mode with "
                          f"{self._task.interval} second interval")
            return
        self.__write_file()

    def self_test(self):
        for i in range(3):
            nonce = self.w3.eth.get_transaction_count(self.address, 'pending')
            base_fee = self.w3.eth.get_block("latest")["baseFeePerGas"]
            tip = self.w3.eth.max_priority_fee
            tx = TxParams({
                'nonce': nonce + i,
                'to': self.address,
                'value': 0,
                'gas': 21000,
                'maxPriorityFeePerGas': tip,
                'maxFeePerGas': base_fee + tip,
                'chainId': 80001,
                'type': '0x2',
                'from': self.address
            })
            self.queue_transaction(tx=tx)
