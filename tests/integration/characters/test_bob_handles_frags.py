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

import pytest
import pytest_twisted
from twisted.internet import threads

from nucypher.characters.lawful import Enrico
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.policy.kits import RetrievalKit

from tests.utils.middleware import MockRestMiddleware, NodeIsDownMiddleware


def test_bob_cannot_follow_the_treasure_map_in_isolation(federated_treasure_map, federated_bob):
    # Assume for the moment that Bob has already received a TreasureMap, perhaps via a side channel.

    # Bob knows of no Ursulas.
    assert len(federated_bob.known_nodes) == 0

    # He can't successfully follow the TreasureMap until he learns of a node to ask.
    unknown, known = federated_bob.peek_at_treasure_map(treasure_map=federated_treasure_map)
    assert len(known) == 0

    # TODO: Show that even with learning loop going, nothing happens here.
    # Probably use Clock?
    federated_bob.follow_treasure_map(treasure_map=federated_treasure_map)
    assert len(known) == 0


def test_bob_already_knows_all_nodes_in_treasure_map(enacted_federated_policy,
                                                     federated_ursulas,
                                                     federated_bob,
                                                     federated_alice):
    # Bob knows of no Ursulas.
    assert len(federated_bob.known_nodes) == 0

    # Now we'll inform Bob of some Ursulas.
    for ursula in federated_ursulas:
        federated_bob.remember_node(ursula)

    # Now, Bob can get the TreasureMap all by himself, and doesn't need a side channel.
    the_map = federated_bob._decrypt_treasure_map(enacted_federated_policy.treasure_map,
                                                  publisher_verifying_key=federated_alice.stamp)
    unknown, known = federated_bob.peek_at_treasure_map(treasure_map=the_map)

    # He finds that he didn't need to discover any new nodes...
    assert len(unknown) == 0

    # ...because he already knew of all the Ursulas on the map.
    assert len(known) == enacted_federated_policy.shares


@pytest_twisted.inlineCallbacks
def test_bob_can_follow_treasure_map_even_if_he_only_knows_of_one_node(federated_treasure_map,
                                                                       federated_ursulas,
                                                                       certificates_tempdir):
    """
    Similar to above, but this time, we'll show that if Bob can connect to a single node, he can
    learn enough to follow the TreasureMap.

    Also, we'll get the TreasureMap from the hrac alone (ie, not via a side channel).
    """

    from nucypher.characters.lawful import Bob

    bob = Bob(network_middleware=MockRestMiddleware(),
              domain=TEMPORARY_DOMAIN,
              start_learning_now=False,
              abort_on_learning_error=True,
              federated_only=True)

    # Again, let's assume that he received the TreasureMap via a side channel.

    # Now, let's create a scenario in which Bob knows of only one node.
    assert len(bob.known_nodes) == 0
    first_ursula = list(federated_ursulas).pop(0)
    bob.remember_node(first_ursula)
    assert len(bob.known_nodes) == 1

    # This time, when he follows the TreasureMap...
    unknown_nodes, known_nodes = bob.peek_at_treasure_map(treasure_map=federated_treasure_map)

    # Bob already knew about one node; the rest are unknown.
    assert len(unknown_nodes) == len(federated_treasure_map) - 1

    # He needs to actually follow the treasure map to get the rest.
    bob.follow_treasure_map(treasure_map=federated_treasure_map)

    # The nodes in the learning loop are now his top target, but he's not learning yet.
    assert not bob._learning_task.running

    # ...so he hasn't learned anything (ie, Bob still knows of just one node).
    assert len(bob.known_nodes) == 1

    # Now, we'll start his learning loop.
    bob.start_learning_loop()

    # ...and block until the unknown_nodes have all been found.
    d = threads.deferToThread(bob.block_until_specific_nodes_are_known, unknown_nodes)
    yield d

    # ...and he now has no more unknown_nodes.
    assert len(bob.known_nodes) == len(federated_treasure_map)
    bob.disenchant()


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        policy_encrypting_key=enacted_policy.public_key,
        label=enacted_policy.label,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
        )


def _make_message_kits(policy_pubkey):
    messages = [b"plaintext1", b"plaintext2", b"plaintext3"]

    message_kits = []
    for message in messages:
        # Using different Enricos, because why not.
        enrico = Enrico(policy_encrypting_key=policy_pubkey)
        message_kit = enrico.encrypt_message(message)
        message_kits.append(message_kit)

    return messages, message_kits


def test_retrieval_kit(enacted_federated_policy, federated_ursulas):
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    capsule = message_kits[0].capsule
    addresses = [ursula.checksum_address for ursula in list(federated_ursulas)[:2]]

    retrieval_kit = RetrievalKit(capsule, addresses)
    serialized = bytes(retrieval_kit)
    retrieval_kit_back = RetrievalKit.from_bytes(serialized)

    assert retrieval_kit.capsule == retrieval_kit_back.capsule
    assert retrieval_kit.queried_addresses == retrieval_kit_back.queried_addresses


def test_single_retrieve(enacted_federated_policy, federated_bob, federated_ursulas):

    federated_bob.start_learning_loop()
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    cleartexts = federated_bob.retrieve(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert cleartexts == messages


def test_use_cached_cfrags(enacted_federated_policy, federated_bob, federated_ursulas):

    federated_bob.start_learning_loop()
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    ursulas = list(federated_ursulas)

    # All Ursulas are down except for two
    federated_bob.network_middleware = NodeIsDownMiddleware()

    for ursula in ursulas[2:]:
        federated_bob.network_middleware.node_is_down(ursula)

    # We can't decrypt, but we still have cfrags from two Ursulas,
    # and we cache them in `federated_bob`
    with pytest.raises(RuntimeError):
        cleartexts = federated_bob.retrieve(
            message_kits=message_kits,
            cache_cfrags=True,
            **_policy_info_kwargs(enacted_federated_policy),
            )

    # Now the remaining two Ursulas go down.
    for ursula in ursulas[:2]:
        federated_bob.network_middleware.node_is_down(ursula)

    # ...but one other comes up.
    federated_bob.network_middleware.node_is_up(ursulas[2])

    # If we don't use the cache, we still can't decrypt - only one cfrag is available.
    with pytest.raises(RuntimeError):
        cleartexts = federated_bob.retrieve(
            message_kits=message_kits,
            **_policy_info_kwargs(enacted_federated_policy),
            )

    # With the cache enabled, we have two cfrags in the cache + one cfrag from the available Ursula
    cleartexts = federated_bob.retrieve(
        message_kits=message_kits,
        use_cached_cfrags=True,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert cleartexts == messages


def test_use_external_cache(enacted_federated_policy, federated_bob, federated_ursulas):

    federated_bob.start_learning_loop()
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    ursulas = list(federated_ursulas)

    # All Ursulas are down except for two
    federated_bob.network_middleware = NodeIsDownMiddleware()
    for ursula in ursulas[2:]:
        federated_bob.network_middleware.node_is_down(ursula)

    # Fetch what we can without decrypting
    loaded_message_kits = federated_bob.retrieve_cfrags(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    # Not enough cfrags yet
    assert not any(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Now the remaining two Ursulas go down.
    for ursula in ursulas[:2]:
        federated_bob.network_middleware.node_is_down(ursula)

    # ...but one other comes up.
    federated_bob.network_middleware.node_is_up(ursulas[2])

    # Try again, building on top of the existing cache
    loaded_message_kits = federated_bob.retrieve_cfrags(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert all(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Should be enough cfrags now. Disconnect all Ursulas
    # to be sure Bob doesn't cheat and contact them again.
    for ursula in ursulas:
        federated_bob.network_middleware.node_is_down(ursula)

    cleartexts = federated_bob.retrieve(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert cleartexts == messages
