"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import itertools
import random
import weakref
from collections import defaultdict
from collections.abc import KeysView
from typing import Optional, Dict, Iterable, List, NamedTuple, Union, Any, Iterator

import maya
from constant_sorrow.constants import UNVERIFIED
from eth_typing import ChecksumAddress

from nucypher.utilities.logging import Logger
from .comprehension import NODE_BUCKETS
from .nicknames import Nickname
from ..crypto.utils import keccak_digest


class ArchivedFleetState(NamedTuple):

    checksum: str
    nickname: Nickname
    timestamp: maya.MayaDT
    population: int

    def to_json(self):
        return dict(checksum=self.checksum,
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
    Fleet state as perceived by a local Ursula.

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
    def new(cls, this_node: Optional['Ursula'] = None) -> 'FleetState':
        this_node_ref = weakref.ref(this_node) if this_node is not None else None
        # Using empty checksum so that JSON library is not confused.
        # Plus, we do need some checksum anyway. It's a legitimate state after all.
        return cls(checksum=keccak_digest(b"").hex(),
                   nodes={},
                   this_node_ref=this_node_ref,
                   this_node_metadata=None)

    def __init__(self,
                 checksum: str,
                 nodes: Dict[ChecksumAddress, 'Ursula'],
                 this_node_ref: Optional[weakref.ReferenceType],
                 this_node_metadata: Optional[bytes]):

        self.checksum = checksum
        self.nickname = Nickname.from_seed(checksum, length=1)
        self._nodes = nodes
        self.timestamp = maya.now()
        self._this_node_ref = this_node_ref
        self._this_node_metadata = this_node_metadata

    def archived(self) -> ArchivedFleetState:
        return ArchivedFleetState(checksum=self.checksum,
                                  nickname=self.nickname,
                                  timestamp=self.timestamp,
                                  population=self.population)

    def _calculate_diff(self,
                        this_node_updated: bool,
                        nodes_to_add: Iterable['Ursula'],
                        nodes_to_remove: Iterable[ChecksumAddress]
                        ) -> StateDiff:

        nodes_updated = []
        for node in nodes_to_add:
            if node.checksum_address in nodes_to_remove:
                continue
            unknown = node.checksum_address not in self._nodes
            if unknown or bytes(self._nodes[node.checksum_address]) != bytes(node):
                nodes_updated.append(node.checksum_address)

        nodes_removed = []
        for checksum_address in nodes_to_remove:
            if checksum_address in self._nodes:
                nodes_removed.append(checksum_address)

        return StateDiff(this_node_updated=this_node_updated,
                         nodes_updated=nodes_updated,
                         nodes_removed=nodes_removed)

    def with_updated_nodes(self,
                           nodes_to_add: Iterable['Ursula'],
                           nodes_to_remove: Iterable[ChecksumAddress],
                           skip_this_node: bool = False,
                           ) -> 'FleetState':

        if self._this_node_ref is not None and not skip_this_node:
            this_node = self._this_node_ref()
            this_node_metadata = bytes(this_node.metadata())
            this_node_updated = self._this_node_metadata != this_node_metadata
            this_node_list = [this_node]
        else:
            this_node_metadata = self._this_node_metadata
            this_node_updated = False
            this_node_list = []

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

            all_nodes_sorted = sorted(itertools.chain(this_node_list, nodes.values()),
                                      key=lambda node: node.checksum_address)
            joined_metadata = b"".join(bytes(node.metadata()) for node in all_nodes_sorted)
            checksum = keccak_digest(joined_metadata).hex()
        else:
            nodes = self._nodes
            checksum = self.checksum

        new_state = FleetState(checksum=checksum,
                               nodes=nodes,
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

    def shuffled(self) -> List['Ursula']:
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
                                                        checksum=self.checksum[:7])

    def __repr__(self):
        return f"FleetState({self.checksum}, {self._nodes}, {self._this_node_ref}, {self._this_node_metadata})"


class FleetSensor:
    """
    A representation of a fleet of NuCypher nodes.

    If `this_node` is provided, it will be included in the state checksum
    (but not returned during iteration/lookups).
    """
    log = Logger("Learning")

    class UnknownLabel(ValueError):
        pass

    class UnknownNode(ValueError):
        pass

    def __init__(self, domain: str, this_node: Optional['Ursula'] = None):

        self._domain = domain

        self._current_state = FleetState.new(this_node)
        self._archived_states = [self._current_state.archived()]
        self._remote_states = {}
        self._remote_last_seen = {}

        # temporary accumulator for new nodes to avoid updating the fleet state every time
        self._nodes_to_add = set()
        self._nodes_to_remove = set()  # Beginning of bucketing.

        self.__marked = defaultdict(set)  # categorization of nodes (bucketing)

        self._auto_update_state = False

    def record_node(self, node: 'Ursula'):

        if node.domain == self._domain:
            # Replace the existing object with a newer object, even if they're equal
            # (this object can be mutated externally).
            # This behavior is supposed to be consistent with that of the node storage
            # (where a newer object with the same `checksum_address` replaces an older one).
            if node in self._nodes_to_add:
                self._nodes_to_add.remove(node)
                # TODO should node be relabelled as unverified here
            self._nodes_to_add.add(node)

            if self._auto_update_state:
                self.log.info(f"Updating fleet state after saving node {node}")
                self.record_fleet_state()

            # ensure node is tracked for labelling
            unlabelled = self.get_label(node.checksum_address) is None
            if unlabelled:
                # Only new nodes - don't relabel prior known nodes here
                self.label(node=node, label=UNVERIFIED)
        else:
            msg = f"Rejected node {node} because its domain is '{node.domain}' but we're only tracking '{self._domain}'"
            self.log.warn(msg)

    def get_node(self, checksum_address: ChecksumAddress, label: Optional = None) -> 'Ursula':
        try:
            node = self._current_state[checksum_address]
        except KeyError:
            raise self.UnknownNode(f'Node {checksum_address} is not already known')
        if label:
            current_label = self.get_label(checksum_address)
            if label == current_label:
                return node
            else:
                raise self.UnknownNode(f'Mismatched label for node {checksum_address}: '
                                       f'expected {label}, actual {current_label}')
        return node

    def get_nodes(self, label: Optional = None) -> Iterator['Ursula']:
        """If label is None return all known nodes"""
        if label is None:
            return iter(self._current_state)

        if label not in NODE_BUCKETS:
            raise self.UnknownLabel(f'{label} is not a valid node label')

        try:
            nodes = [self.get_node(checksum_address) for checksum_address in self.__marked[label]]
        except self.UnknownNode:
            return list()  # empty
        return iter(nodes)

    def __bool__(self):
        return bool(self._current_state)

    def __contains__(self, item):
        """
        Checks if the node *with the same metadata* is recorded in the current state.
        Does not compare ``item`` with the owner node of this FleetSensor.
        """
        return item in self._current_state

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
        return self._archived_states[-previous_states_num-1:-1]

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

    def remove_node(self, node: 'Ursula'):
        # TODO
        pass

    def label(self, node: 'Ursula', label):
        if label not in NODE_BUCKETS:
            raise self.UnknownLabel(f"'{label}' is not a valid node label")

        # node should already be known or is in the nodes_to_add category known
        if (node.checksum_address not in self._current_state) and (node not in self._nodes_to_add):
            raise self.UnknownNode(f"Node {node.checksum_address} is not already known")

        # TODO: a bit of inconsistency between a node being labelled but can't be obtained by `get_node` because
        #  the node is in _nodes_to_add and fleet state not yet recorded
        self.__unlabel(node)
        self.__marked[label].add(node.checksum_address)

    def get_label(self, checksum_address: ChecksumAddress):
        for label in NODE_BUCKETS:
            if checksum_address in self.__marked[label]:
                return label

        return None

    def __unlabel(self, node: 'Ursula'):
        node_labels = []
        for pending_label in NODE_BUCKETS:
            if node.checksum_address in self.__marked[pending_label]:
                self.__marked[pending_label].remove(node.checksum_address)
                node_labels.append(pending_label)
                # could potentially break here - but ensure that node isn't associated with multiple labels

        if len(node_labels) > 1:
            # not the end of the world, but unexpected...
            self.log.warn(f"Unlabelled node ({node}) which originally had multiple labels: {node_labels}")

    def record_remote_fleet_state(self,
                                  checksum_address: ChecksumAddress,
                                  state_checksum: str,
                                  timestamp: maya.MayaDT,
                                  population: int):

        if checksum_address not in self._current_state:
            raise self.UnknownNode(f"Node {checksum_address} is not present in the current fleet state")

        nickname = Nickname.from_seed(state_checksum, length=1)
        state = ArchivedFleetState(checksum=state_checksum,
                                   nickname=nickname,
                                   timestamp=timestamp,
                                   population=population)

        self._remote_last_seen[checksum_address] = maya.now()
        self._remote_states[checksum_address] = state

    def status_info(self, checksum_address_or_node: Union[ChecksumAddress, 'Ursula']) -> 'RemoteUrsulaStatus':

        if isinstance(checksum_address_or_node, str):
            node = self[checksum_address_or_node]
        else:
            node = checksum_address_or_node

        recorded_fleet_state = self._remote_states.get(node.checksum_address, None)
        last_learned_from = self._remote_last_seen.get(node.checksum_address, None)
        worker_address = node.worker_address if node.verified_node else None

        label = self.get_label(node.checksum_address)
        if label is None:
            # should not happen
            raise self.UnknownNode(f"Node {node.checksum_address} is not already known")

        return RemoteUrsulaStatus(label=str(label),
                                  nickname=node.nickname,
                                  staker_address=node.checksum_address,
                                  worker_address=worker_address,
                                  rest_url=node.rest_url(),
                                  timestamp=node.timestamp,
                                  last_learned_from=last_learned_from,
                                  recorded_fleet_state=recorded_fleet_state,
                                  )


class RemoteUrsulaStatus(NamedTuple):
    label: str
    nickname: Nickname
    staker_address: ChecksumAddress
    worker_address: Optional[ChecksumAddress]
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
        return dict(label=self.label,
                    nickname=self.nickname.to_json(),
                    staker_address=self.staker_address,
                    worker_address=self.worker_address,
                    rest_url=self.rest_url,
                    timestamp=self.timestamp.iso8601(),
                    recorded_fleet_state=recorded_fleet_state_json,
                    last_learned_from=last_learned_from_json)
