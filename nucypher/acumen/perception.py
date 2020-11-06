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

import binascii
import random

import maya

from bytestring_splitter import BytestringSplitter
from constant_sorrow.constants import NO_KNOWN_NODES
from collections import namedtuple, defaultdict
from collections import OrderedDict

from .nicknames import Nickname
from nucypher.crypto.api import keccak_digest
from nucypher.utilities.logging import Logger


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

    def __init__(self, domain: str):
        self.domain = domain
        self.additional_nodes_to_track = []
        self.updated = maya.now()
        self._nodes = OrderedDict()
        self._marked = defaultdict(list)  # Beginning of bucketing.
        self.states = OrderedDict()

    def __setitem__(self, checksum_address, node_or_sprout):
        if node_or_sprout.domain == self.domain:
            self._nodes[checksum_address] = node_or_sprout

            if self._tracking:
                self.log.info("Updating fleet state after saving node {}".format(node_or_sprout))
                self.record_fleet_state()
        else:
            msg = f"Rejected node {node_or_sprout} because its domain is '{node_or_sprout.domain}' but we're only tracking '{self.domain}'"
            self.log.warn(msg)

    def __getitem__(self, checksum_address):
        return self._nodes[checksum_address]

    def __bool__(self):
        return bool(self._nodes)

    def __contains__(self, item):
        return item in self._nodes.keys() or item in self._nodes.values()

    def __iter__(self):
        yield from self._nodes.values()

    def __len__(self):
        return len(self._nodes)

    def __eq__(self, other):
        return self._nodes == other._nodes

    def __repr__(self):
        return self._nodes.__repr__()

    def population(self):
        return len(self) + len(self.additional_nodes_to_track)

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
        return self._nodes.keys()

    def snapshot(self):
        fleet_state_checksum_bytes = binascii.unhexlify(self.checksum)
        fleet_state_updated_bytes = self.updated.epoch.to_bytes(4, byteorder="big")
        return fleet_state_checksum_bytes + fleet_state_updated_bytes

    def record_fleet_state(self, additional_nodes_to_track=None):
        if additional_nodes_to_track:
            self.additional_nodes_to_track.extend(additional_nodes_to_track)

        if not self._nodes:
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
        nodes_to_consider = list(self._nodes.values()) + self.additional_nodes_to_track
        return sorted(nodes_to_consider, key=lambda n: n.checksum_address)

    def shuffled(self):
        nodes_we_know_about = list(self._nodes.values())
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

    def mark_as(self, label: Exception, node: "Teacher"):
        self._marked[label].append(node)

        if self._nodes.get(node):
            del self._nodes[node]
