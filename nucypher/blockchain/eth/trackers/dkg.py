import datetime
import json
import os
import time
from json import JSONDecodeError
from tempfile import NamedTemporaryFile
from typing import Callable, List, Optional, Tuple, Set, Dict

import maya
from hexbytes import HexBytes
from prometheus_client import REGISTRY, Gauge
from twisted.internet import threads
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.exceptions import TransactionNotFound
from web3.types import Nonce

# from nucypher.blockchain.eth import actors
from nucypher.blockchain.eth.models import Coordinator
from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.utilities.cache import TTLCache
from nucypher.utilities.events import EventScanner, JSONifiedState
from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask


class EventActuator(EventScanner):
    """Act on events that are found by the scanner."""

    def __init__(
        self,
        hooks: List[Callable],
        clear: bool = True,
        chain_reorg_rescan_window: int = 10,
        *args,
        **kwargs,
    ):
        self.log = Logger("EventActuator")
        if clear and os.path.exists(JSONifiedState.STATE_FILENAME):
            os.remove(JSONifiedState.STATE_FILENAME)
        self.hooks = hooks
        super().__init__(
            chain_reorg_rescan_window=chain_reorg_rescan_window, *args, **kwargs
        )

    def process_event(
        self, event: AttributeDict, get_block_when: Callable[[int], datetime.datetime]
    ):
        for hook in self.hooks:
            try:
                hook(event, get_block_when)
            except Exception as e:
                self.log.warn("Error during event hook: {}".format(e))
                raise
        super().process_event(event, get_block_when)


class EventScannerTask(SimpleTask):
    """Task that runs the event scanner in a looping call."""

    INTERVAL = 120  # seconds

    def __init__(self, scanner: Callable, *args, **kwargs):
        self.scanner = scanner
        super().__init__(*args, **kwargs)

    def run(self):
        self.scanner()

    def handle_errors(self, *args, **kwargs):
        self.log.warn("Error during ritual event scanning: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting event scanner task!")
            self.start(now=False)  # take a breather


class TransactionTracker(SimpleTask):

    INTERVAL = 10
    BLOCK_INTERVAL = 20  # ~20 blocks

    class TransactionFinalized(Exception):
        pass

    class SpendingCapExceeded(Exception):
        pass

    def __init__(
            self,
            w3: Web3,
            transacting_power: "actors.TransactingPower",
            spending_cap: int = 99999999999999999999999999999999999,
            timeout: int = 60 * 60 * 24 * 7,  # 7 days
            tracking_hook: Callable = None,
            finalize_hook: Callable = None,
            *args, **kwargs
    ):
        self.w3 = w3
        self.transacting_power = transacting_power  # TODO: Use LocalAccount instead
        self.address = transacting_power.account

        self.spending_cap = spending_cap
        self.timeout = timeout

        self.__tracking_hook = tracking_hook
        self.__finalize_hook = finalize_hook

        self.__txs: Dict[int, str] = dict()
        self.__file = NamedTemporaryFile(
            mode='w+',
            delete=False,
            encoding='utf-8',
            prefix='txs-cache-',
            suffix='.json',
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
            self.log.warn(f"Replacing tracking txhash #{nonce} | {old} -> {txhash.hex()}")
        else:
            self.log.info(f"Started tracking transaction #{nonce}|{txhash.hex()}")
        self.__txs[int(nonce)] = txhash.hex()

    def __untrack(self, nonce: int) -> None:
        removed_txhash = self.__txs.pop(nonce, None)
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

    def is_tracked(
            self,
            nonce: int = None,
            txhash: HexBytes = None
    ) -> bool:
        tracked = dict(self.tracked)
        if nonce:
            return int(nonce) in tracked
        elif txhash:
            return txhash in tracked.values()
        return False

    @property
    def tracked(self) -> List[Tuple[Nonce, HexBytes]]:
        return [(Nonce(int(nonce)), HexBytes(txhash)) for nonce, txhash in self.__txs.items()]

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
            self.log.info(f"Transaction {txhash.hex()} was reverted by EVM with status {status}")
        self.log.info(f"Transaction {txhash.hex()} has been included in block #{tx.blockNumber}")
        return True

    def _calculate_speedup_fee(self, tx: AttributeDict) -> Tuple[int, int]:
        # Fetch the current base fee and priority fee
        base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
        tip = self.w3.eth.max_priority_fee
        self._log_gas_weather(base_fee, tip)
        factor = 1.2
        increased_tip = round(max(
            tx.maxPriorityFeePerGas,
            tip
        ) * factor)

        fee_per_gas = round(max(
            tx.maxFeePerGas * factor,
            (base_fee * 2) + increased_tip
        ))
        return increased_tip, fee_per_gas

    def _get_average_blocktime(self, sample_window_size: int = 100) -> float:
        """
        Returns the average block time in seconds.
        """
        latest_block = self.w3.eth.get_block('latest')
        if latest_block.number == 0:
            return 0

        # get average block time
        sample_block_number = latest_block.number - sample_window_size
        if sample_block_number <= 0:
            return 0
        base_block = self.w3.eth.get_block(sample_block_number)
        average_block_time = (
            latest_block.timestamp - base_block.timestamp
        ) / sample_window_size
        return average_block_time

    def _log_gas_weather(self, base_fee: int, tip: int) -> None:
        base_fee_gwei = self.w3.from_wei(base_fee, 'gwei')
        tip_gwei = self.w3.from_wei(tip, 'gwei')
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
            'blockHash', 'blockNumber', 'transactionIndex',
            'yParity', 'input', 'gasPrice', 'hash'
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
        tx['maxPriorityFeePerGas'] = tip
        tx['maxFeePerGas'] = max_fee
        tx = AttributeDict(tx)  # disallow mutation
        return tx

    def _calculate_cancel_fee(self, factor: int = 2) -> Tuple[int, int]:
        base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
        tip = self.w3.eth.max_priority_fee * factor
        max_fee = (base_fee * 2) + tip
        return tip, max_fee

    def _make_cancellation_transaction(self, chain_id: int, nonce: int) -> AttributeDict:
        tip, max_fee = self._calculate_cancel_fee()
        tx = AttributeDict({
            'type': '0x2',
            'nonce': nonce,
            'to': self.transacting_power.account,
            'value': 0,
            'gas': 21000,
            'maxPriorityFeePerGas': tip,
            'maxFeePerGas': max_fee,
            'chainId': chain_id,
            'from': self.transacting_power.account
        })
        return tx

    def _handle_transaction_error(self, e: Exception, tx: AttributeDict) -> None:
        rpc_response = e.args[0]
        self.log.critical(f"Transaction #{tx.nonce} | {tx.hash.hex()} "
                          f"failed with { rpc_response['code']} | "
                          f"{rpc_response['message']}")

    def _sign_and_send(self, tx: AttributeDict) -> HexBytes:
        tx = self._prepare_transaction(tx)
        signed_tx = self.transacting_power.sign_transaction(tx)
        try:
            txhash = self.w3.eth.send_raw_transaction(signed_tx)
        except ValueError as e:
            self._handle_transaction_error(e, tx=tx)
        else:
            self.log.info(f"Broadcasted transaction #{tx.nonce} | txhash {txhash.hex()}")
            return txhash

    def speedup_transaction(self, txhash: HexBytes) -> HexBytes:
        tx = self.w3.eth.get_transaction(txhash)
        finalized = self.__is_tx_finalized(tx=tx, txhash=txhash)
        if finalized:
            raise self.TransactionFinalized
        if tx.maxPriorityFeePerGas > self.spending_cap:
            raise self.SpendingCapExceeded
        tx = self._make_speedup_transaction(tx)
        tip, base_fee = tx.maxPriorityFeePerGas, tx.maxFeePerGas
        self._log_gas_weather(base_fee, tip)
        self.log.info(f"Speeding up transaction #{tx.nonce} with "
                      f"maxPriorityFeePerGas={tip} and maxFeePerGas={base_fee}")
        txhash = self._sign_and_send(tx)
        return txhash

    def cancel_transaction(self, nonce: int) -> HexBytes:
        tx = self._make_cancellation_transaction(nonce=nonce, chain_id=self.w3.eth.chain_id)
        tx = self._prepare_transaction(tx)
        self.log.info(f"Cancelling transaction #{nonce} with "
                      f"tip: {tx.maxPriorityFeePerGas} and fee: {tx.maxFeePerGas}")
        txhash = self._sign_and_send(tx)
        return txhash

    def cancel_transactions(self, nonces: Set[int]) -> None:
        self.log.info(f"Cancelling {len(nonces)} transactions")
        txs = set()
        for nonce in nonces:
            txhash = self.cancel_transaction(nonce=nonce)
            txs.add((nonce, txhash))
            time.sleep(0.5)
        self.track(txs=txs)

    def start(self, now: bool = False):
        self.log.info("Starting Transaction Tracker")
        pending_nonce = self.w3.eth.get_transaction_count(self.address, 'pending')
        latest_nonce = self.w3.eth.get_transaction_count(self.address, 'latest')
        pending = pending_nonce - latest_nonce
        pending_nonces = range(latest_nonce, pending_nonce)
        self.log.info(f"Detected {pending} pending transactions "
                      f"with nonces {', '.join(map(str, pending_nonces))}")
        self._restore_state(pending_nonces)
        self._handle_untracked_transactions(pending_nonces)

        average_block_time = self._get_average_blocktime()
        self._task.interval = round(average_block_time * self.BLOCK_INTERVAL)
        self.log.info(f"Average block time is {average_block_time} seconds")
        self.log.info(f"Set tracking interval to {self._task.interval} seconds")

        super().start(now=now)

    def _handle_untracked_transactions(self, pending_nonces):
        untracked_nonces = set(filter(lambda n: not self.is_tracked(nonce=n), pending_nonces))
        if len(untracked_nonces) > 0:
            # Cancels all pending transactions that are not tracked
            self.log.warn(f"Detected {len(untracked_nonces)} untracked "
                          f"pending transactions with nonces {', '.join(map(str, untracked_nonces))}")
            self.cancel_transactions(nonces=untracked_nonces)

    def _restore_state(self, pending_nonces) -> None:
        """Read the pending transaction data from the disk"""
        records = self.__read_file()
        if len(records) > 0:
            disk_txhashes = '\n'.join(f'#{nonce}|{txhash.hex()}' for nonce, txhash in records.items())
            self.log.debug(f"Loaded {len(records)} tracked txhashes "
                           f"with nonces {', '.join(map(str, records.keys()))} "
                           f"from disk\n{disk_txhashes}")
        if not pending_nonces:
            self.log.info("No pending transactions to track")
        elif set(records) == set(pending_nonces):
            self.log.info("All cached transactions are tracked")
        else:
            diff = set(pending_nonces) - set(records)
            self.log.warn("Untracked nonces: {}".format(', '.join(map(str, diff))))
        self.track(txs=set(records.items()))

    def run(self):
        if len(self.tracked) == 0:
            self.log.info(f"Steady as she goes... next cycle in {self.INTERVAL} seconds")
            return False
        self.log.info(f"Tracking {len(self.tracked)} transaction{'s' if len(self.tracked) > 1 else ''}")

        replacements, finalized = set(), set()
        for nonce, txhash in self.tracked:
            # NOTE: do not mutate __txs while iterating over it.
            try:
                replacement_txhash = self.speedup_transaction(txhash)
                replacements.add((nonce, replacement_txhash))
            except self.TransactionFinalized:
                finalized.add(nonce)
                continue
            except self.SpendingCapExceeded:
                self.log.warn(f"Transaction #{nonce} exceeds spending cap.")
                continue
            except TransactionNotFound:
                # TODO not sure what to do here - mark for removal.
                finalized.add((nonce, txhash))
                self.log.info(f"Transaction #{nonce}|{txhash.hex()} not found")
                continue

        # Update the cache
        self.track(txs=replacements)
        self.untrack(nonces=finalized)

        if replacements:
            self.log.info(f"Replaced {len(replacements)} transactions")
        if finalized:
            self.log.info(f"Finalized {len(finalized)} transactions")

    def handle_errors(self, *args, **kwargs):
        self.log.warn("Error during transaction: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting transaction task!")
            self.start(now=False)  # take a breather


class ActiveRitualTracker:

    MAX_CHUNK_SIZE = 10000

    # how often to check/purge for expired cached values - 8hrs?
    _PARTICIPATION_STATES_PURGE_INTERVAL = 60 * 60 * 8

    # what's the buffer for potentially receiving repeated events - 10mins?
    _RITUAL_TIMEOUT_ADDITIONAL_TTL_BUFFER = 60 * 10

    _LAST_SCANNED_BLOCK_METRIC = Gauge(
        "ritual_events_last_scanned_block_number",
        "Last scanned block number for ritual events",
        registry=REGISTRY,
    )

    class ParticipationState:
        def __init__(
            self,
            participating=False,
            already_posted_transcript=False,
            already_posted_aggregate=False,
        ):
            self.participating = participating
            self.already_posted_transcript = already_posted_transcript
            self.already_posted_aggregate = already_posted_aggregate

    def __init__(
        self,
        operator: "actors.Operator",
        persistent: bool = False,  # TODO: use persistent storage?
    ):
        self.log = Logger("RitualTracker")

        self.operator = operator
        self.coordinator_agent = operator.coordinator_agent

        # Restore/create persistent event scanner state
        self.persistent = persistent
        self.state = JSONifiedState(persistent=persistent)
        self.state.restore()

        # Map events to handlers
        self.actions = {
            self.contract.events.StartRitual: self.operator.perform_round_1,
            self.contract.events.StartAggregationRound: self.operator.perform_round_2,
        }

        self.events = [
            self.contract.events.StartRitual,
            self.contract.events.StartAggregationRound,
            self.contract.events.EndRitual,
        ]

        # ritual id -> phase -> txhash
        self.active_phase_txs: Dict[int, Tuple[int, int]] = dict()

        # TODO: Remove the default JSON-RPC retry middleware
        # as it correctly cannot handle eth_getLogs block range throttle down.
        # self.web3.middleware_onion.remove(http_retry_request_middleware)

        self.scanner = EventActuator(
            hooks=[self._handle_ritual_event],
            web3=self.web3,
            state=self.state,
            contract=self.contract,
            events=self.events,
            filters={"address": self.contract.address},
            # How many maximum blocks at the time we request from JSON-RPC,
            # and we are unlikely to exceed the response size limit of the JSON-RPC server
            max_chunk_scan_size=self.MAX_CHUNK_SIZE
        )

        self.task = EventScannerTask(scanner=self.scan)

        cache_ttl = (
            self.coordinator_agent.get_timeout()
            + self._RITUAL_TIMEOUT_ADDITIONAL_TTL_BUFFER
        )
        self._participation_states = TTLCache(
            ttl=cache_ttl
        )  # { ritual_id -> ParticipationState }
        self._participation_states_next_purge_timestamp = maya.now().add(
            seconds=self._PARTICIPATION_STATES_PURGE_INTERVAL
        )

    @property
    def provider(self):
        return self.web3.provider

    @property
    def web3(self):
        return self.coordinator_agent.blockchain.w3

    @property
    def contract(self):
        return self.coordinator_agent.contract
    
    def remove_active_ritual_phase_txs(self, nonces: List[int]) -> None:
        data = {}
        for rid, (nonce, txhash) in self.active_phase_txs.items():
            if nonce in nonces:
                continue
            data[rid] = (nonce, txhash)
        self.active_phase_txs = data

    def add_active_ritual_phase_txs(self, ritual_id: int, txs: List[Tuple[int, int]]) -> None:
        for nonce, txhash in txs:
            self.active_phase_txs[ritual_id] = (nonce, txhash)

    # TODO: should sample_window_size be additionally configurable/chain-dependent?
    def _get_first_scan_start_block_number(self, sample_window_size: int = 100) -> int:
        """
        Returns the block number to start scanning for events from.
        """
        w3 = self.web3
        timeout = self.coordinator_agent.get_timeout()

        latest_block = w3.eth.get_block('latest')
        if latest_block.number == 0:
            return 0

        # get average block time
        sample_block_number = latest_block.number - sample_window_size
        if sample_block_number <= 0:
            return 0
        base_block = w3.eth.get_block(sample_block_number)
        average_block_time = (
            latest_block.timestamp - base_block.timestamp
        ) / sample_window_size

        number_of_blocks_in_the_past = int(timeout / average_block_time)

        expected_start_block = w3.eth.get_block(
            max(0, latest_block.number - number_of_blocks_in_the_past)
        )
        target_timestamp = latest_block.timestamp - timeout

        # Keep looking back until we find the last block before the target timestamp
        while (
            expected_start_block.number > 0
            and expected_start_block.timestamp > target_timestamp
        ):
            expected_start_block = w3.eth.get_block(expected_start_block.number - 1)

        # if non-zero block found - return the block before
        return expected_start_block.number - 1 if expected_start_block.number > 0 else 0

    def start(self):
        """Start the event scanner task."""
        return self.task.start()

    def stop(self):
        """Stop the event scanner task."""
        return self.task.stop()

    def _action_required(self, ritual_event: AttributeDict) -> bool:
        """Check if an action is required for a given ritual event."""
        # establish participation state first
        participation_state = self._get_participation_state(ritual_event)

        if not participation_state.participating:
            return False

        # does event have an associated action
        event_type = getattr(self.contract.events, ritual_event.event)

        event_has_associated_action = event_type in self.actions
        already_posted_transcript = (
            event_type == self.contract.events.StartRitual
            and participation_state.already_posted_transcript
        )
        already_posted_aggregate = (
            event_type == self.contract.events.StartAggregationRound
            and participation_state.already_posted_aggregate
        )
        if any(
            [
                not event_has_associated_action,
                already_posted_transcript,
                already_posted_aggregate,
            ]
        ):
            return False

        return True

    def _get_ritual_participant_info(
        self, ritual_id: int
    ) -> Optional[Coordinator.Participant]:
        """
        Returns node's participant information for the provided
        ritual id; None if node is not participating in the ritual
        """
        is_participant = self.coordinator_agent.is_participant(
            ritual_id=ritual_id, provider=self.operator.checksum_address
        )
        if is_participant:
            participant = self.coordinator_agent.get_participant(
                ritual_id=ritual_id,
                provider=self.operator.checksum_address,
                transcript=True,
            )
            return participant

        return None

    def _purge_expired_participation_states_as_needed(self):
        # let's check whether we should purge participation states before returning
        now = maya.now()
        if now > self._participation_states_next_purge_timestamp:
            self._participation_states.purge_expired()
            self._participation_states_next_purge_timestamp = now.add(
                seconds=self._PARTICIPATION_STATES_PURGE_INTERVAL
            )

    def _get_participation_state_values_from_contract(
        self, ritual_id: int
    ) -> Tuple[bool, bool, bool]:
        """
        Obtains values for ParticipationState from the Coordinator contract.
        """
        participating = False
        already_posted_transcript = False
        already_posted_aggregate = False

        participant_info = self._get_ritual_participant_info(ritual_id=ritual_id)
        if participant_info:
            # actually participating in this ritual; get latest information
            participating = True
            # populate information since we already hit the contract
            already_posted_transcript = bool(participant_info.transcript)
            already_posted_aggregate = participant_info.aggregated

        return participating, already_posted_transcript, already_posted_aggregate

    def _get_participation_state(self, event: AttributeDict) -> ParticipationState:
        """
        Returns the current participation state of the Operator as it pertains to
        the ritual associated with the provided event.
        """
        self._purge_expired_participation_states_as_needed()

        event_type = getattr(self.contract.events, event.event)
        if event_type not in self.events:
            # should never happen since we specify the list of events we
            # want to receive (1st level of filtering)
            raise RuntimeError(f"Unexpected event type: {event_type}")

        args = event.args

        try:
            ritual_id = args.ritualId
        except AttributeError:
            # no ritualId arg
            raise RuntimeError(
                f"Unexpected event type: '{event_type}' has no ritual id as argument"
            )

        participation_state = self._participation_states[ritual_id]
        if not participation_state:
            # not previously tracked; get current state and return
            # need to determine if participating in this ritual or not
            if event_type == self.contract.events.StartRitual:
                participation_state = self.ParticipationState(
                    participating=(self.operator.checksum_address in args.participants)
                )
                self._participation_states[ritual_id] = participation_state
                return participation_state

            # obtain information from contract
            (
                participating,
                posted_transcript,
                posted_aggregate,
            ) = self._get_participation_state_values_from_contract(ritual_id=ritual_id)
            participation_state = self.ParticipationState(
                participating=participating,
                already_posted_transcript=posted_transcript,
                already_posted_aggregate=posted_aggregate,
            )
            self._participation_states[ritual_id] = participation_state
            return participation_state

        # already tracked but not participating
        if not participation_state.participating:
            return participation_state

        #
        # already tracked and participating in ritual - populate other values
        #
        if event_type == self.contract.events.StartAggregationRound:
            participation_state.already_posted_transcript = True
        elif event_type == self.contract.events.EndRitual:
            # while `EndRitual` signals the end of the ritual, and there is no
            # *current* node action for EndRitual, perhaps there will
            # be one in the future. So to be complete, and adhere to
            # the expectations of this function we still update
            # the participation state
            if args.successful:
                # since successful we know these values are true
                participation_state.already_posted_transcript = True
                participation_state.already_posted_aggregate = True
            elif (
                not participation_state.already_posted_transcript
                or not participation_state.already_posted_aggregate
            ):
                # not successful - and unsure of state values
                # obtain information from contract
                (
                    _,  # participating ignored - we know we are participating
                    posted_transcript,
                    posted_aggregate,
                ) = self._get_participation_state_values_from_contract(
                    ritual_id=ritual_id
                )
                participation_state.already_posted_transcript = posted_transcript
                participation_state.already_posted_aggregate = posted_aggregate

        return participation_state

    def __execute_action(
        self,
        ritual_event: AttributeDict,
        timestamp: int,
        defer: bool = False,
    ):
        """Execute a round of a ritual asynchronously."""
        # NOTE: this format splits on *capital letters* and converts to snake case
        #  so "StartConfirmationRound" becomes "start_confirmation_round"
        #  do not use abbreviations in event names (e.g. "DKG" -> "d_k_g")
        formatted_kwargs = {
            camel_case_to_snake(k): v for k, v in ritual_event.args.items()
        }
        event_type = getattr(self.contract.events, ritual_event.event)
        def task():
            self.actions[event_type](timestamp=timestamp, **formatted_kwargs)
        if defer:
            d = threads.deferToThread(task)
            d.addErrback(self.task.handle_errors)
            return d
        else:
            return task()

    def _handle_ritual_event(
        self,
        ritual_event: AttributeDict,
        get_block_when: Callable[[int], datetime.datetime],
    ):
        # is event actionable
        if not self._action_required(ritual_event):
            self.log.debug(
                f"Event '{ritual_event.event}', does not require further action either: not participating in ritual, no corresponding action or previously handled; skipping"
            )
            return

        timestamp = int(get_block_when(ritual_event.blockNumber).timestamp())
        d = self.__execute_action(ritual_event=ritual_event, timestamp=timestamp)
        return d

    def __scan(self, start_block, end_block, account):
        # Run the scan
        self.log.debug(f"({account[:8]}) Scanning events in block range {start_block} - {end_block}")
        start = time.time()
        result, total_chunks_scanned = self.scanner.scan(start_block, end_block)
        if self.persistent:
            self.state.save()
        duration = time.time() - start
        self.log.debug(f"Scanned total of {len(result)} events, in {duration} seconds, "
                       f"total {total_chunks_scanned} chunk scans performed")

    def scan(self):
        """
        Assume we might have scanned the blocks all the way to the last Ethereum block
        that mined a few seconds before the previous scan run ended.
        Because there might have been a minor Ethereum chain reorganisations since the last scan ended,
        we need to discard the last few blocks from the previous scan results.
        """
        last_scanned_block = self.scanner.get_last_scanned_block()
        self._LAST_SCANNED_BLOCK_METRIC.set(last_scanned_block)

        if last_scanned_block == 0:
            # first run so calculate starting block number based on dkg timeout
            suggested_start_block = self._get_first_scan_start_block_number()
        else:
            self.scanner.delete_potentially_forked_block_data(
                last_scanned_block - self.scanner.chain_reorg_rescan_window
            )
            suggested_start_block = self.scanner.get_suggested_scan_start_block()

        end_block = self.scanner.get_suggested_scan_end_block()
        self.__scan(
            suggested_start_block, end_block, self.operator.transacting_power.account
        )
