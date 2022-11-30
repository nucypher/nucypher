


import datetime

import maya
import pytest

from nucypher.characters.lawful import Enrico, Ursula
from nucypher.characters.unlawful import Amonia


@pytest.mark.skip("FIXME - DISABLED FOR TDEC ADAPTATION DEVELOPMENT")
def test_try_to_post_free_service_by_hacking_enact(
    ursulas, alice, bob, agency, testerchain
):
    """
    This time we won't rely on the tabulation in Alice's enact() to catch the problem.
    """
    amonia = Amonia.from_lawful_alice(alice)
    # Set up the policy details
    shares = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"another_path"

    bupkiss_policy = amonia.circumvent_safegaurds_and_grant_without_paying(
        bob=bob, label=label, threshold=2, shares=shares, expiration=policy_end_datetime
    )

    # Enrico becomes
    enrico = Enrico(policy_encrypting_key=bupkiss_policy.public_key)
    plaintext = b"A crafty campaign"
    message_kit = enrico.encrypt_message(plaintext)

    with pytest.raises(
        Ursula.NotEnoughUrsulas
    ):  # Return a more descriptive request error?
        bob.retrieve_and_decrypt(
            [message_kit],
            alice_verifying_key=amonia.stamp.as_umbral_pubkey(),
            encrypted_treasure_map=bupkiss_policy.treasure_map,
        )
