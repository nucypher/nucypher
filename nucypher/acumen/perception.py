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
from collections import namedtuple
from collections import OrderedDict
from twisted.logger import Logger

from .nicknames import nickname_from_seed
from nucypher.crypto.api import keccak_digest


def icon_from_checksum(checksum,
                       nickname_metadata,
                       number_of_nodes="Unknown number of "):
    if checksum is NO_KNOWN_NODES:
        return "NO FLEET STATE AVAILABLE"
    icon_template = """
    <div class="nucypher-nickname-icon" style="border-color:{color};">
    <div class="small">{number_of_nodes} nodes</div>
    <div class="symbols">
        <span class="single-symbol" style="color: {color}">{symbol}&#xFE0E;</span>
    </div>
    <br/>
    <span class="small-address">{fleet_state_checksum}</span>
    </div>
    """.replace("  ", "").replace('\n', "")
    return icon_template.format(
        number_of_nodes=number_of_nodes,
        color=nickname_metadata[0][0]['hex'],
        symbol=nickname_metadata[0][1],
        fleet_state_checksum=checksum[0:8]
    )


class FleetSensor:
    """
    A representation of a fleet of NuCypher nodes.
    """
    _checksum = NO_KNOWN_NODES.bool_value(False)
    _nickname = NO_KNOWN_NODES
    _nickname_metadata = NO_KNOWN_NODES
    _tracking = False
    most_recent_node_change = NO_KNOWN_NODES
    snapshot_splitter = BytestringSplitter(32, 4)
    log = Logger("Learning")
    FleetState = namedtuple("FleetState", ("nickname", "metadata", "icon", "nodes", "updated"))

    def __init__(self):
        self.additional_nodes_to_track = []
        self.updated = maya.now()
        self._nodes = OrderedDict()
        self.states = OrderedDict()

    def __setitem__(self, key, value):
        self._nodes[key] = value

        if self._tracking:
            self.log.info("Updating fleet state after saving node {}".format(value))
            self.record_fleet_state()

    def __getitem__(self, item):
        return self._nodes[item]

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

    @property
    def checksum(self):
        return self._checksum

    @checksum.setter
    def checksum(self, checksum_value):
        self._checksum = checksum_value
        self._nickname, self._nickname_metadata = nickname_from_seed(checksum_value, number_of_pairs=1)

    @property
    def nickname(self):
        return self._nickname

    @property
    def nickname_metadata(self):
        return self._nickname_metadata

    @property
    def icon(self) -> str:
        if self.nickname_metadata is NO_KNOWN_NODES:
            return str(NO_KNOWN_NODES)
        return self.nickname_metadata[0][1]

    def addresses(self):
        return self._nodes.keys()

    def icon_html(self):
        return icon_from_checksum(checksum=self.checksum,
                                  number_of_nodes=str(len(self)),
                                  nickname_metadata=self.nickname_metadata)

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
                                        metadata=self.nickname_metadata,
                                        nodes=sorted_nodes,
                                        icon=self.icon,
                                        updated=self.updated)
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
        return {"nickname": state.nickname,
                "symbol": state.metadata[0][1],
                "color_hex": state.metadata[0][0]['hex'],
                "color_name": state.metadata[0][0]['color'],
                "updated": state.updated.rfc2822(),
                }
