import maya
import datetime
import os
import pytest

from constant_sorrow.constants import NO_DECRYPTION_PERFORMED

from nucypher.characters.lawful import Bob, Ursula
from nucypher.characters.lawful import Enrico
from nucypher.keystore.keypairs import SigningKeypair
from nucypher.policy.models import TreasureMap
from nucypher.utilities.sandbox.constants import NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK, MOCK_POLICY_DEFAULT_M
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def test_federated_bob_retrieves(federated_ursulas,
                                 federated_bob,
                                 federated_alice,
                                 capsule_side_channel,
                                 enacted_federated_policy
                                 ):

    # Assume for the moment that Bob has already received a TreasureMap.
    treasure_map = enacted_federated_policy.treasure_map
    federated_bob.treasure_maps[treasure_map.public_id()] = treasure_map

    for ursula in federated_ursulas:
        federated_bob.remember_node(ursula)

    # The side channel delivers all that Bob needs at this point:
    # - A single MessageKit, containing a Capsule
    # - A representation of the data source
    the_message_kit, the_data_source = capsule_side_channel

    alices_verifying_key = federated_alice.stamp.as_umbral_pubkey()

    delivered_cleartexts = federated_bob.retrieve(message_kit=the_message_kit,
                                                  data_source=the_data_source,
                                                  alice_verifying_key=alices_verifying_key)

    # We show that indeed this is the passage originally encrypted by the Enrico.
    assert b"Welcome to the flippering." == delivered_cleartexts[0]


def test_bob_joins_policy_and_retrieves(federated_alice,
                                        federated_ursulas,
                                        certificates_tempdir,
                                        ):

    # Let's partition Ursulas in two parts
    a_couple_of_ursulas = list(federated_ursulas)[:2]
    rest_of_ursulas = list(federated_ursulas)[2:]

    # Bob becomes
    bob = Bob(federated_only=True,
              start_learning_now=True,
              network_middleware=MockRestMiddleware(),
              abort_on_learning_error=True,
              known_nodes=a_couple_of_ursulas,
              )

    # Bob only knows a couple of Ursulas initially
    assert len(bob.known_nodes) == 2

    # Alice creates a policy granting access to Bob
    # Just for fun, let's assume she distributes KFrags among Ursulas unknown to Bob
    n = NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK - 2
    label = b'label://' + os.urandom(32)
    contract_end_datetime = maya.now() + datetime.timedelta(days=5)
    policy = federated_alice.grant(bob=bob,
                                   label=label,
                                   m=3,
                                   n=n,
                                   expiration=contract_end_datetime,
                                   handpicked_ursulas=set(rest_of_ursulas),
                                   )

    assert bob == policy.bob
    assert label == policy.label

    # Now, Bob joins the policy
    bob.join_policy(label=label,
                    alice_pubkey_sig=federated_alice.stamp,
                    )

    # In the end, Bob should know all the Ursulas
    assert len(bob.known_nodes) == len(federated_ursulas)

    # Enrico becomes
    enrico = Enrico(policy_encrypting_key=policy.public_key,
                             label=label
                             )

    plaintext = b"What's your approach?  Mississippis or what?"
    message_kit, _signature = enrico.encrypt_message(plaintext)

    alices_verifying_key = federated_alice.stamp.as_umbral_pubkey()

    # Bob takes the message_kit and retrieves the message within
    delivered_cleartexts = bob.retrieve(message_kit=message_kit,
                                        data_source=enrico,
                                        alice_verifying_key=alices_verifying_key)

    assert plaintext == delivered_cleartexts[0]

    # Let's try retrieve again, but Alice revoked the policy.
    failed_revocations = federated_alice.revoke(policy)
    assert len(failed_revocations) == 0

    with pytest.raises(Ursula.NotEnoughUrsulas):
        _cleartexts = bob.retrieve(message_kit=message_kit,
                                   data_source=enrico,
                                   alice_verifying_key=alices_verifying_key)


def test_treasure_map_serialization(enacted_federated_policy, federated_bob):
    treasure_map = enacted_federated_policy.treasure_map
    assert treasure_map.m != None
    assert treasure_map.m != NO_DECRYPTION_PERFORMED
    assert treasure_map.m == MOCK_POLICY_DEFAULT_M, 'm value is not correct'

    serialized_map = bytes(treasure_map)
    deserialized_map = TreasureMap.from_bytes(serialized_map)
    assert deserialized_map._hrac == treasure_map._hrac

    # TreasureMap is currently encrypted
    with pytest.raises(TypeError):
        deserialized_map.m

    with pytest.raises(TypeError):
        deserialized_map.destinations

    compass = federated_bob.make_compass_for_alice(
                                            enacted_federated_policy.alice)
    deserialized_map.orient(compass)
    assert deserialized_map.m == treasure_map.m
    assert deserialized_map.destinations == treasure_map.destinations
