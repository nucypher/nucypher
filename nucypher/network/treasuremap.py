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
from random import shuffle

import maya
from nucypher.crypto.umbral_adapter import PublicKey

from nucypher.acumen.perception import FleetSensor
from nucypher.crypto.signing import InvalidSignature
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.nodes import Learner


def get_treasure_map_from_known_ursulas(learner: Learner,
                                        map_identifier: str,
                                        bob_encrypting_key: PublicKey,
                                        timeout=3):
    """
    Iterate through the nodes we know, asking for the TreasureMap.
    Return the first one who has it.
    """
    if learner.federated_only:
        from nucypher.policy.maps import TreasureMap as _MapClass
    else:
        from nucypher.policy.maps import SignedTreasureMap as _MapClass

    start = maya.now()

    # Spend no more than half the timeout finding the nodes.  8 nodes is arbitrary.  Come at me.
    learner.block_until_number_of_known_nodes_is(8, timeout=timeout / 2, learn_on_this_thread=True)
    while True:
        nodes_with_map = find_matching_nodes(known_nodes=learner.known_nodes, bob_encrypting_key=bob_encrypting_key)
        # TODO nodes_with_map can be large - what if treasure map not present in any of them? Without checking the
        #  timeout within the loop, this could take a long time.
        shuffle(nodes_with_map)

        for node in nodes_with_map:
            try:
                response = learner.network_middleware.get_treasure_map_from_node(node, map_identifier)
            except (*NodeSeemsToBeDown, learner.NotEnoughNodes):
                continue
            except learner.network_middleware.NotFound:
                learner.log.info(f"Node {node} claimed not to have TreasureMap {map_identifier}")
                continue
            except node.NotStaking:
                # TODO this wasn't here before - check with myles
                learner.log.info(f"Node {node} not staking")
                continue

            if response.status_code == 200 and response.content:
                try:
                    treasure_map = _MapClass.from_bytes(response.content)
                    return treasure_map
                except InvalidSignature:
                    # TODO: What if a node gives a bunk TreasureMap?  NRN
                    raise
            else:
                continue  # TODO: Actually, handle error case here.  NRN
        else:
            learner.learn_from_teacher_node()

        if (start - maya.now()).seconds > timeout:
            raise _MapClass.NowhereToBeFound(f"Asked {len(learner.known_nodes)} nodes, "
                                             f"but none had map {map_identifier}")


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
