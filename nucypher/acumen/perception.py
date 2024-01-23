import random
import weakref
from collections import deque
from collections.abc import KeysView
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Union

import maya
from eth_typing import ChecksumAddress
from nucypher_core import FleetStateChecksum, NodeMetadata

from nucypher import characters
from nucypher.acumen.nicknames import Nickname
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.utilities.logging import Logger


class ArchivedFleetState(NamedTuple):

    checksum: str
    nickname: Nickname
    timestamp: maya.MayaDT
    population: int

    def to_json(self):
        return dict(checksum=bytes(self.checksum).hex(),
                    nickname=self.nickname.to_json(),
                    timestamp=self.timestamp.rfc2822(),
                    population=self.population)


class StateDiff(NamedTuple):
    this_node_updated: bool
    nodes_updated: List[ChecksumAddress]
    nodes_removed: List[ChecksumAddress]

    def empty(self):
        return not self.this_node_updated and not self.nodes_updated and not self.nodes_removed


class FleetState:
    """
    Fleet state as perceived by a local "Ursula".

    Assumptions we're based on:

    - Every supplied node object, after its constructor has finished,
      has a ``.checksum_address`` and ``bytes()`` (metadata)
    - checksum address or metadata do not change for the same Python object
    - ``this_node`` (the owner of FleetSensor) may not have metadata initially
      (when the constructor is first called), but will have one at the time of the first
      `record_fleet_state()` call.
    - The metadata of ``this_node`` **can** change.
    - For the purposes of the fleet state, nodes with different metadata are considered different,
      even if they have the same checksum address.
    """

    @classmethod
    def new(
        cls, this_node: Optional["characters.lawful.Ursula"] = None
    ) -> "FleetState":
        this_node_ref = weakref.ref(this_node) if this_node else None
        # `this_node` might not have its metadata available yet.
        this_node_metadata = None

        return cls(nodes={},
                   this_node_ref=this_node_ref,
                   this_node_metadata=this_node_metadata)

    def __init__(
        self,
        nodes: Dict[ChecksumAddress, "characters.lawful.Ursula"],
        this_node_ref: Optional[weakref.ReferenceType],
        this_node_metadata: Optional[NodeMetadata],
    ):
        self.checksum = FleetStateChecksum(
            this_node=this_node_metadata,
            other_nodes=[node.metadata() for node in nodes.values()],
        )
        self.nickname = Nickname.from_seed(bytes(self.checksum), length=1)
        self._nodes = nodes
        self.timestamp = maya.now()
        self._this_node_ref = this_node_ref
        self._this_node_metadata = this_node_metadata

    def archived(self) -> ArchivedFleetState:
        return ArchivedFleetState(checksum=self.checksum,
                                  nickname=self.nickname,
                                  timestamp=self.timestamp,
                                  population=self.population)

    def _calculate_diff(
        self,
        this_node_updated: bool,
        nodes_to_add: Iterable["characters.lawful.Ursula"],
        nodes_to_remove: Iterable[ChecksumAddress],
    ) -> StateDiff:
        nodes_updated = []
        for node in nodes_to_add:
            if node.checksum_address in nodes_to_remove:
                continue
            unknown = node.checksum_address not in self._nodes
            if unknown or bytes(self._nodes[node.checksum_address].metadata()) != bytes(node.metadata()):
                nodes_updated.append(node.checksum_address)

        nodes_removed = []
        for checksum_address in nodes_to_remove:
            if checksum_address in self._nodes:
                nodes_removed.append(checksum_address)

        return StateDiff(this_node_updated=this_node_updated,
                         nodes_updated=nodes_updated,
                         nodes_removed=nodes_removed)

    def with_updated_nodes(
        self,
        nodes_to_add: Iterable["characters.lawful.Ursula"],
        nodes_to_remove: Iterable[ChecksumAddress],
        skip_this_node: bool = False,
    ) -> "FleetState":
        if self._this_node_ref is not None and not skip_this_node:
            this_node = self._this_node_ref()
            this_node_metadata = this_node.metadata()
            this_node_updated = self._this_node_metadata != this_node_metadata
        else:
            this_node_metadata = self._this_node_metadata
            this_node_updated = False

        diff = self._calculate_diff(this_node_updated, nodes_to_add, nodes_to_remove)

        if not diff.empty():
            # TODO: if nodes were kept in a Merkle tree,
            # we'd have to only recalculate log(N) checksums.
            # Is it worth it?
            nodes = dict(self._nodes)
            nodes_to_add_dict = {node.checksum_address: node for node in nodes_to_add}
            for checksum_address in diff.nodes_updated:
                new_node = nodes_to_add_dict[checksum_address]
                nodes[checksum_address] = new_node
            for checksum_address in diff.nodes_removed:
                del nodes[checksum_address]
        else:
            nodes = self._nodes

        new_state = FleetState(nodes=nodes,
                               this_node_ref=self._this_node_ref,
                               this_node_metadata=this_node_metadata)

        return new_state, diff

    @property
    def population(self) -> int:
        """Returns the number of all known nodes, including itself, if applicable."""
        return len(self) + int(self._this_node_metadata is not None)

    def __getitem__(self, checksum_address):
        return self._nodes[checksum_address]

    def addresses(self) -> KeysView:
        return self._nodes.keys()

    def __bool__(self):
        return len(self) != 0

    def __contains__(self, item):
        if isinstance(item, str):
            return item in self._nodes
        else:
            return item.checksum_address in self._nodes

    def __iter__(self):
        yield from self._nodes.values()

    def __len__(self):
        return len(self._nodes)

    def shuffled(self) -> List["characters.lawful.Ursula"]:
        nodes_we_know_about = list(self._nodes.values())
        random.shuffle(nodes_we_know_about)
        return nodes_we_know_about

    def to_json(self) -> Dict:
        return dict(nickname=self.nickname.to_json(),
                    updated=self.timestamp.rfc2822())

    @property
    def icon(self) -> str:
        return self.nickname.icon

    def items(self):
        return self._nodes.items()

    def values(self):
        return self._nodes.values()

    def __str__(self):
        return '{checksum} ⇀{nickname}↽ {icon} '.format(icon=self.nickname.icon,
                                                        nickname=self.nickname,
                                                        checksum=bytes(self.checksum).hex()[:7])

    def __repr__(self):
        return f"FleetState({self.checksum}, {self._nodes}, {self._this_node_ref}, {self._this_node_metadata})"


class FleetSensor:
    """
    A representation of a fleet of nodes.

    If `this_node` is provided, it will be included in the state checksum
    (but not returned during iteration/lookups).
    """
    log = Logger("Learning")

    def __init__(
        self, domain: TACoDomain, this_node: Optional["characters.lawful.Ursula"] = None
    ):
        self._domain = domain

        self._current_state = FleetState.new(this_node)
        self._archived_states = deque([self._current_state.archived()], maxlen=5)
        self._remote_states = {}
        self._remote_last_seen = {}

        # temporary accumulator for new nodes to avoid updating the fleet state every time
        self._nodes_to_add = set()
        self._nodes_to_remove = set()  # Beginning of bucketing.

        self._auto_update_state = False

    def record_node(self, node: "characters.lawful.Ursula"):

        if str(node.domain) == str(self._domain):
            # Replace the existing object with a newer object, even if they're equal
            # (this object can be mutated externally).
            # This behavior is supposed to be consistent with that of the node storage
            # (where a newer object with the same `checksum_address` replaces an older one).
            if node in self._nodes_to_add:
                self._nodes_to_add.remove(node)
            self._nodes_to_add.add(node)

            if self._auto_update_state:
                self.log.info(f"Updating fleet state after saving node {node}")
                self.record_fleet_state()
        else:
            msg = f"Rejected node {node} because its domain is '{node.domain}' but we're only tracking '{self._domain}'"
            self.log.warn(msg)

    def __getitem__(self, item):
        return self._current_state[item]

    def __bool__(self):
        return bool(self._current_state)

    def __contains__(self, item):
        """
        Checks if the node *with the same metadata* is recorded in the current state.
        Does not compare ``item`` with the owner node of this FleetSensor.
        """
        return item in self._current_state

    def __iter__(self):
        yield from self._current_state

    def __len__(self):
        return len(self._current_state)

    def __repr__(self):
        return f"FleetSensor({self._current_state.__repr__()})"

    @property
    def current_state(self):
        return self._current_state

    @property
    def checksum(self):
        return self._current_state.checksum

    @property
    def population(self):
        return self._current_state.population

    @property
    def nickname(self):
        return self._current_state.nickname

    @property
    def icon(self) -> str:
        return self._current_state.icon

    @property
    def timestamp(self):
        return self._current_state.timestamp

    def items(self):
        return self._current_state.items()

    def values(self):
        return self._current_state.values()

    def latest_state(self) -> ArchivedFleetState:
        # `_archived_states` is never empty, one state is created in the constructor
        return self._archived_states[-1]

    def previous_states(self, quantity: int) -> List[ArchivedFleetState]:
        """
        Returns at most ``quantity`` latest archived states (*not* including the current one),
        in chronological order.
        """
        # `_archived_states` is never empty, one state is created in the constructor
        previous_states_num = min(len(self._archived_states) - 1, quantity)
        return list(self._archived_states)[-previous_states_num-1:-1]

    def addresses(self):
        return self._current_state.addresses()

    def record_fleet_state(self, skip_this_node: bool = False) -> StateDiff:
        new_state, diff = self._current_state.with_updated_nodes(nodes_to_add=self._nodes_to_add,
                                                                 nodes_to_remove=self._nodes_to_remove,
                                                                 skip_this_node=skip_this_node)

        self._nodes_to_add = set()
        self._nodes_to_remove = set()
        self._current_state = new_state

        # TODO: set a limit on the number of archived states?
        # Two ways to collect archived states:
        # 1. (current) add a state to the archive every time it changes
        # 2. (possible) keep a dictionary of known states
        #    and bump the timestamp of a previously encountered one
        if not diff.empty():
            archived_state = new_state.archived()
            self._archived_states.append(archived_state)

        return diff

    def shuffled(self):
        return self._current_state.shuffled()

    def mark_as(self, label: Exception, node: "characters.lawful.Ursula"):
        # TODO: for now we're not using `label` in any way, so we're just ignoring it
        self._nodes_to_remove.add(node.checksum_address)

    def record_remote_fleet_state(self,
                                  checksum_address: ChecksumAddress,
                                  state_checksum: FleetStateChecksum,
                                  timestamp: maya.MayaDT,
                                  population: int):

        if checksum_address not in self._current_state:
            raise KeyError(f"A node {checksum_address} is not present in the current fleet state")

        nickname = Nickname.from_seed(bytes(state_checksum), length=1)
        state = ArchivedFleetState(checksum=state_checksum,
                                   nickname=nickname,
                                   timestamp=timestamp,
                                   population=population)

        self._remote_last_seen[checksum_address] = maya.now()
        self._remote_states[checksum_address] = state

    def status_info(
        self,
        checksum_address_or_node: Union[ChecksumAddress, "characters.lawful.Ursula"],
    ) -> "RemoteUrsulaStatus":
        if isinstance(checksum_address_or_node, str):
            node = self[checksum_address_or_node]
        else:
            node = checksum_address_or_node

        recorded_fleet_state = self._remote_states.get(node.checksum_address, None)
        last_learned_from = self._remote_last_seen.get(node.checksum_address, None)
        operator_address = node.operator_address if node.verified_node else None

        return RemoteUrsulaStatus(verified=node.verified_node,
                                  nickname=node.nickname,
                                  staker_address=node.checksum_address,
                                  operator_address=operator_address,
                                  rest_url=node.rest_url(),
                                  timestamp=node.timestamp,
                                  last_learned_from=last_learned_from,
                                  recorded_fleet_state=recorded_fleet_state,
                                  )


class RemoteUrsulaStatus(NamedTuple):
    verified: bool
    nickname: Nickname
    staker_address: ChecksumAddress
    operator_address: Optional[ChecksumAddress]
    rest_url: str
    timestamp: maya.MayaDT
    recorded_fleet_state: Optional[ArchivedFleetState]
    last_learned_from: Optional[maya.MayaDT]

    def to_json(self) -> Dict[str, Any]:
        if self.recorded_fleet_state is None:
            recorded_fleet_state_json = None
        else:
            recorded_fleet_state_json = self.recorded_fleet_state.to_json()
        if self.last_learned_from is None:
            last_learned_from_json = None
        else:
            last_learned_from_json = self.last_learned_from.iso8601()
        return dict(verified=self.verified,
                    nickname=self.nickname.to_json(),
                    staker_address=self.staker_address,
                    operator_address=self.operator_address,
                    rest_url=self.rest_url,
                    timestamp=self.timestamp.iso8601(),
                    recorded_fleet_state=recorded_fleet_state_json,
                    last_learned_from=last_learned_from_json)
