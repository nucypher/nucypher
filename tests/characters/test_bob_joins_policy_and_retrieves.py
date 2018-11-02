import maya
import datetime
import os

from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.characters.lawful import Bob
from nucypher.data_sources import DataSource
from nucypher.utilities.sandbox.constants import DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK
from nucypher.keystore.keypairs import SigningKeypair


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

    # We show that indeed this is the passage originally encrypted by the DataSource.
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
              known_certificates_dir=certificates_tempdir,
              abort_on_learning_error=True,
              known_nodes=a_couple_of_ursulas,
              )

    # Bob only knows a couple of Ursulas initially
    assert len(bob.known_nodes) == 2

    # Alice creates a policy granting access to Bob
    # Just for fun, let's assume she distributes KFrags among Ursulas unknown to Bob
    n = DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK - 2
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

    # DataSource becomes
    data_source = DataSource(policy_pubkey_enc=policy.public_key,
                             signing_keypair=SigningKeypair(),
                             label=label
                             )

    plaintext = b"What's your approach?  Mississippis or what?"
    message_kit, _signature = data_source.encapsulate_single_message(plaintext)

    alices_verifying_key = federated_alice.stamp.as_umbral_pubkey()

    # Bob takes the message_kit and retrieves the message within
    delivered_cleartexts = bob.retrieve(message_kit=message_kit,
                                        data_source=data_source,
                                        alice_verifying_key=alices_verifying_key)

    assert plaintext == delivered_cleartexts[0]
