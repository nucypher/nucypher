import datetime
import os
import time

import maya
import pytest
from twisted.internet.task import Clock

from nucypher.characters.lawful import Bob, Enrico
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import (
    MOCK_ETH_PROVIDER_URI,
    NUMBER_OF_URSULAS_IN_DEVELOPMENT_DOMAIN,
)
from tests.utils.middleware import MockRestMiddleware


def test_bob_full_retrieve_flow(
    ursulas, bob, alice, capsule_side_channel, treasure_map, enacted_policy
):

    for ursula in ursulas:
        bob.remember_node(ursula)

    # The side channel delivers all that Bob needs at this point:
    # - A single MessageKit, containing a Capsule
    # - A representation of the data source
    the_message_kit = capsule_side_channel()
    alices_verifying_key = alice.stamp.as_umbral_pubkey()

    delivered_cleartexts = bob.retrieve_and_decrypt(
        [the_message_kit],
        alice_verifying_key=alices_verifying_key,
        encrypted_treasure_map=enacted_policy.treasure_map,
    )

    # We show that indeed this is the passage originally encrypted by the Enrico.
    assert b"Welcome to flippering number 0." == delivered_cleartexts[0]


def test_bob_retrieves(alice, ursulas, certificates_tempdir):
    """A test to show that Bob can retrieve data from Ursula"""

    # Let's partition Ursulas in two parts
    a_couple_of_ursulas = list(ursulas)[:2]
    rest_of_ursulas = list(ursulas)[2:]

    # Bob becomes
    bob = Bob(
        domain=TEMPORARY_DOMAIN,
        start_learning_now=True,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        network_middleware=MockRestMiddleware(eth_endpoint=MOCK_ETH_PROVIDER_URI),
        abort_on_learning_error=True,
        known_nodes=a_couple_of_ursulas,
    )

    # Bob has only connected to - at most - 2 nodes.
    assert sum(node.verified_node for node in bob.known_nodes) <= 2

    # Alice creates a policy granting access to Bob
    # Just for fun, let's assume she distributes KFrags among Ursulas unknown to Bob
    shares = NUMBER_OF_URSULAS_IN_DEVELOPMENT_DOMAIN - 2
    label = b'label://' + os.urandom(32)
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    policy = alice.grant(
        bob=bob,
        label=label,
        threshold=3,
        shares=shares,
        expiration=contract_end_datetime,
        ursulas=set(rest_of_ursulas),
    )

    assert label == policy.label

    # Enrico becomes
    enrico = Enrico(encrypting_key=policy.public_key)

    plaintext = b"What's your approach?  Mississippis or what?"
    message_kit = enrico.encrypt_for_pre(plaintext)

    alices_verifying_key = alice.stamp.as_umbral_pubkey()

    # Bob takes the message_kit and retrieves the message within
    delivered_cleartexts = bob.retrieve_and_decrypt([message_kit],
                                                    alice_verifying_key=alices_verifying_key,
                                                    encrypted_treasure_map=policy.treasure_map)

    assert plaintext == delivered_cleartexts[0]

    cleartexts_delivered_a_second_time = bob.retrieve_and_decrypt([message_kit],
                                                                  alice_verifying_key=alices_verifying_key,
                                                                  encrypted_treasure_map=policy.treasure_map)

    # Indeed, they're the same cleartexts.
    assert delivered_cleartexts == cleartexts_delivered_a_second_time

    # Let's try retrieve again, but Alice revoked the policy.
    receipt, failed_revocations = alice.revoke(policy)
    assert len(failed_revocations) == 0

    # One thing to note here is that Bob *can* still retrieve with the cached CFrags,
    # even though this Policy has been revoked.  #892
    _cleartexts = bob.retrieve_and_decrypt([message_kit],
                                           alice_verifying_key=alices_verifying_key,
                                           encrypted_treasure_map=policy.treasure_map)
    assert _cleartexts == delivered_cleartexts  # TODO: 892

    bob.disenchant()


def test_bob_retrieves_with_treasure_map(
    bob, ursulas, enacted_policy, capsule_side_channel
):
    message_kit = capsule_side_channel()
    treasure_map = enacted_policy.treasure_map
    alice_verifying_key = enacted_policy.publisher_verifying_key

    # Teach Bob about the network
    bob.remember_node(list(ursulas)[0])
    bob.learn_from_teacher_node(eager=True)

    # Deserialized treasure map
    text1 = bob.retrieve_and_decrypt(
        [message_kit],
        alice_verifying_key=alice_verifying_key,
        encrypted_treasure_map=treasure_map)

    assert text1 == [b'Welcome to flippering number 1.']


# TODO: #2813 Without kfrag and arrangement storage by nodes,
@pytest.mark.skip()
def test_bob_retrieves_too_late(bob, ursulas, enacted_policy, capsule_side_channel):
    clock = Clock()
    clock.advance(time.time())
    clock.advance(86400 * 8)  # 1 week  # TODO: this is supposed to be seven days, not eight

    message_kit = capsule_side_channel()
    treasure_map = enacted_policy.treasure_map
    alice_verifying_key = enacted_policy.publisher_verifying_key

    # with pytest.raises(Ursula.NotEnoughUrsulas):
    bob.retrieve_and_decrypt(
        [message_kit],
        alice_verifying_key=alice_verifying_key,
        encrypted_treasure_map=treasure_map
    )
