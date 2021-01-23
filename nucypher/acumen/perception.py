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


import random
import weakref
from collections.abc import KeysView
from typing import Optional, Dict, Iterable, List, Tuple

import binascii
import itertools
import maya
from bytestring_splitter import BytestringSplitter
from eth_typing import ChecksumAddress

from nucypher.crypto.api import keccak_digest
from nucypher.utilities.logging import Logger
from .nicknames import Nickname


class ArchivedFleetState:

    def __init__(self, checksum: str, nickname: Nickname, timestamp: maya.MayaDT, population: int):
        self.checksum = checksum
        self.nickname = nickname
        self.timestamp = timestamp
        self.population = population

    def to_json(self):
        return dict(checksum=self.checksum,
                    nickname=self.nickname.to_json(),
                    timestamp=self.timestamp.rfc2822(),
                    population=self.population)


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

    def _remote_nodes_updated(self,
                              nodes_to_add: Iterable['Ursula'],
                              nodes_to_remove: Iterable[ChecksumAddress]
                              ) -> bool:

        for node in nodes_to_add:
            if node.checksum_address in nodes_to_remove:
                continue
            if node.checksum_address not in self._nodes:
                return True
            if bytes(self._nodes[node.checksum_address]) != bytes(node):
                return True

        for checksum_address in nodes_to_remove:
            if checksum_address in self._nodes:
                return True

        return False

    def with_updated_nodes(self,
                           nodes_to_add: Iterable['Ursula'],
                           nodes_to_remove: Iterable[ChecksumAddress],
                           skip_this_node: bool = False,
                           ) -> 'FleetState':

        if self._this_node_ref is not None and not skip_this_node:
            this_node = self._this_node_ref()
            this_node_metadata = bytes(this_node)
            this_node_changed = self._this_node_metadata != this_node_metadata
            this_node_list = [this_node]
        else:
            this_node_metadata = self._this_node_metadata
            this_node_changed = False
            this_node_list = []

        remote_nodes_updated = self._remote_nodes_updated(nodes_to_add, nodes_to_remove)

        if this_node_changed or remote_nodes_updated:
            # TODO: if nodes were kept in a Merkle tree,
            # we'd have to only recalculate log(N) checksums.
            # Is it worth it?
            nodes = dict(self._nodes)
            for node in nodes_to_add:
                nodes[node.checksum_address] = node
            for checksum_address in nodes_to_remove:
                if checksum_address in nodes:
                    del nodes[checksum_address]

            all_nodes_sorted = sorted(itertools.chain(this_node_list, nodes.values()),
                                      key=lambda node: node.checksum_address)
            joined_metadata = b"".join(bytes(node) for node in all_nodes_sorted)
            checksum = keccak_digest(joined_metadata).hex()
        else:
            nodes = self._nodes
            checksum = self.checksum

        return FleetState(checksum=checksum,
                          nodes=nodes,
                          this_node_ref=self._this_node_ref,
                          this_node_metadata=this_node_metadata)

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

    # TODO: we only send it along with `FLEET_STATES_MATCH`, so it is essentially useless.
    # But it's hard to change now because older nodes will be looking for it.
    def snapshot(self) -> bytes:
        checksum_bytes = binascii.unhexlify(self.checksum)
        timestamp_bytes = self.timestamp.epoch.to_bytes(4, byteorder="big")
        return checksum_bytes + timestamp_bytes

    snapshot_splitter = BytestringSplitter(32, 4)

    @staticmethod
    def unpack_snapshot(data) -> Tuple[str, maya.MayaDT, bytes]:
        checksum_bytes, timestamp_bytes, remainder = FleetState.snapshot_splitter(data, return_remainder=True)
        checksum = checksum_bytes.hex()
        timestamp = maya.MayaDT(int.from_bytes(timestamp_bytes, byteorder="big"))
        return checksum, timestamp, remainder

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

    def __init__(self, domain: str, this_node: Optional['Ursula'] = None):

        self._domain = domain

        self._current_state = FleetState.new(this_node)
        self._archived_states = [self._current_state.archived()]
        self.remote_states = {}

        # temporary accumulator for new nodes to avoid updating the fleet state every time
        self._nodes_to_add = set()
        self._nodes_to_remove = set()  # Beginning of bucketing.

        self._auto_update_state = False

    def record_node(self, node: 'Ursula'):

        if node.domain == self._domain:
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

    def latest_states(self, quantity: int) -> List[ArchivedFleetState]:
        """
        Returns at most ``quantity`` latest archived states (including the current one),
        in chronological order.
        """
        latest = self._archived_states[-min(len(self._archived_states), quantity):]
        return latest

    def addresses(self):
        return self._current_state.addresses()

    def snapshot(self):
        return self._current_state.snapshot()

    @staticmethod
    def unpack_snapshot(data):
        return FleetState.unpack_snapshot(data)

    def record_fleet_state(self, skip_this_node: bool = False):
        new_state = self._current_state.with_updated_nodes(nodes_to_add=self._nodes_to_add,
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
        if new_state.checksum != self._archived_states[-1].checksum:
            self._archived_states.append(new_state.archived())

    def shuffled(self):
        return self._current_state.shuffled()

    def mark_as(self, label: Exception, node: 'Ursula'):
        # TODO: for now we're not using `label` in any way, so we're just ignoring it
        self._nodes_to_remove.add(node.checksum_address)

    def record_remote_fleet_state(self,
                                  checksum_address: ChecksumAddress,
                                  state_checksum: str,
                                  timestamp: maya.MayaDT,
                                  population: int):
        nickname = Nickname.from_seed(state_checksum, length=1)
        self.remote_states[checksum_address] = ArchivedFleetState(checksum=state_checksum,
                                                                  nickname=nickname,
                                                                  timestamp=timestamp,
                                                                  population=population)
