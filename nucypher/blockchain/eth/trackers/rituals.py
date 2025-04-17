from abc import ABC, abstractmethod
from typing import Callable, Dict, List

import maya
from web3 import Web3
from web3.contract import Contract
from web3.contract.contract import ContractEvent
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.trackers.events import EventTracker
from nucypher.blockchain.eth.utils import get_block_just_before
from nucypher.utilities.cache import TTLCache


class RitualTracker(EventTracker, ABC):
    # how often to check/purge for expired cached values - 8hrs?
    _PARTICIPATION_STATES_PURGE_INTERVAL = 60 * 60 * 8

    # what's the buffer for potentially receiving repeated events - 10mins?
    _TIMEOUT_ADDITIONAL_TTL_BUFFER = 60 * 10

    class ParticipationState:
        def __init__(
            self,
            participating=False,
        ):
            self.participating = participating

    def __init__(
        self,
        operator,
        web3: Web3,
        contract: Contract,
        events: List[ContractEvent],
        actions: Dict[ContractEvent, Callable],
        timeout: int,
        persistent: bool = False,
    ):
        super().__init__(
            operator=operator,
            web3=web3,
            contract=contract,
            events=events,
            actions=actions,
            persistent=persistent,
        )
        self.timeout = timeout

        cache_ttl = timeout + self._TIMEOUT_ADDITIONAL_TTL_BUFFER
        self._participation_states = TTLCache(
            ttl=cache_ttl
        )  # { id -> ParticipationState }
        self._participation_states_next_purge_timestamp = maya.now().add(
            seconds=self._PARTICIPATION_STATES_PURGE_INTERVAL
        )

    @abstractmethod
    def _get_identifier(self, event: AttributeDict) -> str:
        """
        Returns the identifier for the event.
        """
        raise NotImplementedError

    @abstractmethod
    def _action_required_based_on_participation_state(
        self, participation_state: ParticipationState, event: AttributeDict
    ):
        raise NotImplementedError

    @abstractmethod
    def _create_participation_state(self, event: AttributeDict) -> ParticipationState:
        """
        Returns a new instance of the participation state class.
        """
        raise NotImplementedError

    @abstractmethod
    def _update_participation_state(
        self, participation_state: ParticipationState, event: AttributeDict
    ) -> None:
        """
        Updates the participation state with the information from the event.
        """
        raise NotImplementedError

    def _get_first_scan_start_block_number(self, sample_window_size: int = 100) -> int:
        """
        Returns the block number to start scanning for events from.
        """
        return get_block_just_before(
            w3=self.web3,
            how_far_back=self.timeout,
            sample_window_size=sample_window_size,
        )

    def _action_required(self, event: AttributeDict) -> bool:
        """Check if an action is required for a given ritual event."""
        # establish participation state first
        participation_state = self._get_participation_state(event)

        if not participation_state.participating:
            return False

        return self._action_required_based_on_participation_state(
            participation_state, event
        )

    def _purge_expired_participation_states_as_needed(self):
        # let's check whether we should purge participation states before returning
        now = maya.now()
        if now > self._participation_states_next_purge_timestamp:
            self._participation_states.purge_expired()
            self._participation_states_next_purge_timestamp = now.add(
                seconds=self._PARTICIPATION_STATES_PURGE_INTERVAL
            )

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

        try:
            identifier = self._get_identifier(event)
        except AttributeError:
            # no ritualId arg
            raise RuntimeError(
                f"Unexpected event type: '{event_type}' has no id attribute"
            )

        participation_state = self._participation_states[identifier]
        if not participation_state:
            participation_state = self._create_participation_state(event)
            self._participation_states[identifier] = participation_state
            return participation_state

        # already tracked but not participating
        if participation_state.participating:
            # already tracked and participating in ritual - populate other values if necessary
            self._update_participation_state(participation_state, event)

        return participation_state
