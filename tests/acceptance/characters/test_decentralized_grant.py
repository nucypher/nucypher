


import datetime
import os

import maya
from nucypher_core import EncryptedKeyFrag

from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.policy.payment import SubscriptionManagerPayment
from tests.constants import TEST_ETH_PROVIDER_URI

shares = 3
policy_end_datetime = maya.now() + datetime.timedelta(days=35)


def check(policy, bob, ursulas):

    # Check the generated treasure map is decryptable by Bob.
    treasure_map = bob._decrypt_treasure_map(policy.treasure_map, policy.publisher_verifying_key)

    # The number of actual destinations is exactly equal to shares.
    assert len(treasure_map.destinations) == shares

    # Let's look at the destinations.
    for ursula in ursulas:
        if ursula.canonical_address in treasure_map.destinations:
            kfrag_kit = treasure_map.destinations[ursula.canonical_address]
            assert isinstance(kfrag_kit, EncryptedKeyFrag)
            # TODO: try to decrypt?


def test_decentralized_grant_subscription_manager(blockchain_alice, blockchain_bob, blockchain_ursulas):
    payment_method = SubscriptionManagerPayment(eth_provider=TEST_ETH_PROVIDER_URI, network=TEMPORARY_DOMAIN)
    blockchain_alice.payment_method = payment_method
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=os.urandom(16),
                                    threshold=2,
                                    shares=shares,
                                    expiration=policy_end_datetime)
    check(policy=policy, bob=blockchain_bob, ursulas=blockchain_ursulas)
