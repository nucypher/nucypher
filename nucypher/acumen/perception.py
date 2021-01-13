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

from collections import OrderedDict
from collections import namedtuple, defaultdict

import binascii
import maya
import random
from bytestring_splitter import BytestringSplitter
from constant_sorrow.constants import (
    NO_KNOWN_NODES,
    UNVERIFIED,
    VERIFIED,
    UNAVAILABLE,
    SUSPICIOUS,
    UNSTAKED,
    INVALID
)
from typing import Iterator, Callable, List, Dict, Type, Optional

from nucypher.crypto.api import keccak_digest
from nucypher.utilities.logging import Logger
from .nicknames import Nickname
from .pruning import construct_node_stalecheck, reject_node, accept_node, construct_node_max_attempts


class FleetSensor:
    """
    A representation of a fleet of NuCypher nodes.
    """
    _checksum = NO_KNOWN_NODES.bool_value(False)
    _nickname = NO_KNOWN_NODES
    _tracking = False
    most_recent_node_change = NO_KNOWN_NODES
    snapshot_splitter = BytestringSplitter(32, 4)
    log = Logger("Learning")
    FleetState = namedtuple("FleetState", ("nickname", "icon", "nodes", "updated", "checksum"))

    BUCKETS = (
        # NUCYPHER / SUPERNODE / SEEDNODE,
        UNVERIFIED,
        VERIFIED,
        UNAVAILABLE,
        SUSPICIOUS,
        UNSTAKED,
        INVALID
    )

    # Buckets that do not need pruning
    # UNVERIFIED
    # VERIFIED
    # SEEDNODE

    __three_days = 60*60*72
    __pruning_strategies = {
        UNAVAILABLE: [
            construct_node_stalecheck(max_seconds=__three_days),
            construct_node_max_attempts(max_attempts=20)
        ],
        SUSPICIOUS: [reject_node],
        UNSTAKED: [accept_node],
        INVALID: [accept_node],
    }

    class UnknownLabel(KeyError):
        pass

    class UnknownNode(ValueError):
        pass

    def __init__(self, domain: str, discovery_labels=None):

        # Public
        self.domain = domain
        self.discovery_labels = discovery_labels  # TODO: Only track certain labels?
        self.additional_nodes_to_track = []
        self.updated = maya.now()

        # Private
        self.__states = OrderedDict()
        self.__nodes = OrderedDict()       # memory.  # TODO: keep both collections or reduce to use one?
        self.__marked = defaultdict(list)  # bucketing.

    def __setitem__(self, checksum_address, node_or_sprout):
        if node_or_sprout.domain == self.domain:
            self.__nodes[checksum_address] = node_or_sprout

            if self._tracking:
                self.log.info("Updating fleet state after saving node {}".format(node_or_sprout))
                self.record_fleet_state()
        else:
            msg = f"Rejected node {node_or_sprout} because its domain is '{node_or_sprout.domain}' but we're only tracking '{self.domain}'"
            self.log.warn(msg)

    def __getitem__(self, checksum_address):
        return self.__nodes[checksum_address]

    def __bool__(self):
        return bool(self.__nodes)

    def __contains__(self, item):
        return item in self.__nodes.keys() or item in self.__nodes.values()

    def __iter__(self):
        yield from self.__nodes.values()

    def __len__(self):
        return len(self.__nodes)

    def __eq__(self, other):
        return self.__nodes == other.__nodes

    def __repr__(self):
        return self.__nodes.__repr__()

    def population(self):
        return len(self) + len(self.additional_nodes_to_track)

    @property
    def states(self):
        return self.__states

    @property
    def checksum(self):
        return self._checksum

    @checksum.setter
    def checksum(self, checksum_value):
        self._checksum = checksum_value
        self._nickname = Nickname.from_seed(checksum_value, length=1)

    @property
    def nickname(self):
        return self._nickname

    @property
    def icon(self) -> str:
        if self.nickname is NO_KNOWN_NODES:
            return str(NO_KNOWN_NODES)
        return self.nickname.icon

    def addresses(self):
        return self.__nodes.keys()

    def snapshot(self):
        fleet_state_checksum_bytes = binascii.unhexlify(self.checksum)
        fleet_state_updated_bytes = self.updated.epoch.to_bytes(4, byteorder="big")
        return fleet_state_checksum_bytes + fleet_state_updated_bytes

    def record_fleet_state(self, additional_nodes_to_track=None):
        if additional_nodes_to_track:
            self.additional_nodes_to_track.extend(additional_nodes_to_track)

        if not self.__nodes:
            # No news here.
            return
        sorted_nodes = self.sorted()

        sorted_nodes_joined = b"".join(bytes(n) for n in sorted_nodes)
        checksum = keccak_digest(sorted_nodes_joined).hex()
        if checksum not in self.states:
            self.checksum = keccak_digest(b"".join(bytes(n) for n in self.sorted())).hex()
            self.updated = maya.now()
            # For now we store the sorted node list.  Someday we probably spin this out into
            # its own class, FleetState, and use it as the basis for partial updates.
            new_state = self.FleetState(nickname=self.nickname,
                                        nodes=sorted_nodes,
                                        icon=self.icon,
                                        updated=self.updated,
                                        checksum=self.checksum)
            self.states[checksum] = new_state
            return checksum, new_state

    def start_tracking_state(self, additional_nodes_to_track=None):
        if additional_nodes_to_track is None:
            additional_nodes_to_track = list()
        self.additional_nodes_to_track.extend(additional_nodes_to_track)
        self._tracking = True
        self.update_fleet_state()

    def sorted(self):
        nodes_to_consider = list(self.__nodes.values()) + self.additional_nodes_to_track
        return sorted(nodes_to_consider, key=lambda n: n.checksum_address)

    def shuffled(self):
        nodes_we_know_about = list(self.__nodes.values())
        random.shuffle(nodes_we_know_about)
        return nodes_we_know_about

    def abridged_states_dict(self):
        abridged_states = {}
        for k, v in self.states.items():
            abridged_states[k] = self.abridged_state_details(v)
        return abridged_states

    @staticmethod
    def abridged_state_details(state):
        return {"nickname": str(state.nickname),
                # FIXME: generalize in case we want to extend the number of symbols in the state nickname
                "symbol": state.nickname.characters[0].symbol,
                "color_hex": state.nickname.characters[0].color_hex,
                "color_name": state.nickname.characters[0].color_name,
                "updated": state.updated.rfc2822(),
                }

    def __reset_node_label_tracking(self, node: "Teacher"):
        for strategy in self.__pruning_strategies:
            strategy(node=node, reset=True)

    def register_node_pruning_strategy(self,
                                       label,
                                       strategy: Callable,
                                       layer: Optional[int] = None
                                       ) -> None:
        if label not in self.BUCKETS:
            raise self.UnknownLabel
        try:
            existing_strategies = self.__pruning_strategies[label]
        except KeyError:
            raise ValueError(f"{label} is not a prunable node bucket.")
        if strategy in existing_strategies:
            raise ValueError(f"Strategy is already registered for bucket '{label}'.")
        if layer is None:
            existing_strategies.append(strategy)
        else:
            existing_strategies.insert(strategy, index=layer)

    def get_nodes(self, label=None) -> Iterator["Teacher"]:
        """If label is None return all know nodes"""
        if not label:
            return iter(self)
        if label not in self.BUCKETS:
            raise self.UnknownLabel(f'{label} is not a valid node label')
        try:
            nodes = self.__marked[label]
        except KeyError:
            return iter(dict())  # empty
        return iter(nodes)

    def label(self, label, node: "Teacher") -> None:
        """
        Apply a label to a known node.  Removes any exiting labels before adding the new one.
        If the provided label is not valid UnknownLabel is raised.
        If the provided node is not known UnknownNode is raised.
        """
        if label not in self.BUCKETS:
            raise self.UnknownLabel(f'{label} is not a valid node label')
        if self.__nodes.get(node.checksum_address):
            self.unlabel(node=node)            # Remove any existing labels...
            self.__marked[label].append(node)  # Set the new label
        else:
            raise self.UnknownNode(f'Cannot label an unknown node ({node}).')

    def unlabel(self, node: "Teacher", label=None) -> None:
        """Removes a label from a node, or if label is None, all labels are removed."""

        # Remove one label
        if label:
            if node in self.__marked[label]:
                self.__marked[label].remove(node)
                return

        # Remove all labels
        for _label in self.BUCKETS:
            if node in self.__marked[_label]:
                self.__marked[_label].remove(node)

    def prune_bucket(self, label):
        """Apply pruning strategies to a single node bucket once"""
        try:
            strategies = self.__pruning_strategies[label]
        except KeyError:
            raise self.UnknownLabel
        for node in self.get_nodes(label=label):
            for strategy in strategies:
                keep = strategy(node=node)
                if not keep:
                    del self.__nodes[node.checksum_address]  # prune node
                    self.unlabel(node=node, label=label)     # prune corresponding label
                    break  # this node is already doomed anyways
                    # TODO: forget node from disk too
                    # TODO: Trash can label?
            else:
                # Reinstate this node to good standing by un/relabeling
                if label in self.__pruning_strategies:
                    self.unlabel(node=node, label=label)
                    self.__reset_node_label_tracking(node=node)

    def prune_nodes(self) -> None:
        """Apply node pruning strategies to all marked nodes once"""
        self._pruning_strategies: Dict[type, List[Callable]]
        for label in self._pruning_strategies:
            self.prune_bucket(label=label)
