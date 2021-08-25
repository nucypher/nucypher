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

from nucypher.acumen.perception import FleetSensor
from nucypher.crypto.umbral_adapter import PublicKey
from nucypher.network.nodes import Learner


def find_matching_nodes(known_nodes: FleetSensor,
                        bob_encrypting_key: PublicKey,
                        no_less_than=7):  # Somewhat arbitrary floor here.
    # Look for nodes whose checksum address has the second character of Bob's encrypting key in the first
    # few characters.
    # Think of it as a cheap knockoff hamming distance.
    # The good news is that Bob can construct the list easily.
    # And - famous last words incoming - there's no cognizable attack surface.
    # Sure, Bob can mine encrypting keypairs until he gets the set of target Ursulas on which Alice can
    # store a TreasureMap.  And then... ???... profit?

    # Sanity check - do we even have enough nodes?
    if len(known_nodes) < no_less_than:
        raise ValueError(f"Can't select {no_less_than} from {len(known_nodes)} (Fleet state: {known_nodes.FleetState})")

    search_boundary = 2
    target_nodes = []
    target_hex_match = bytes(bob_encrypting_key).hex()[1]
    while len(target_nodes) < no_less_than:
        search_boundary += 2
        if search_boundary > 42:  # We've searched the entire string and can't match any.  TODO: Portable learning is a nice idea here.
            # Not enough matching nodes.  Fine, we'll just publish to the first few.
            try:
                # TODO: This is almost certainly happening in a test.  If it does happen in production, it's a
                #  bit of a problem.  Need to fix #2124 to mitigate.
                target_nodes = list(known_nodes.values())[0:6]
                return target_nodes
            except IndexError:
                raise Learner.NotEnoughNodes(
                    "There aren't enough nodes on the network to enact this policy.  Unless this is day "
                    "one of the network and nodes are still getting spun up, something is bonkers.")

        # TODO: 1995 all throughout here (we might not (need to) know the checksum address yet; canonical will do.)
        # This might be a performance issue above a few thousand nodes.
        target_nodes = [node for node in known_nodes if target_hex_match in node.checksum_address[2:search_boundary]]
    return target_nodes
