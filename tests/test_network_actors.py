

def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():


    pk_alice =
    sk_alice =

    pk_ursula =
    sk_ursula =

    # TODO: In the real world, this will be a fingerprint of alice's pk, followed by a hash of the path.
    policy_id =

    # TODO: In the real world, this will be a kFrag, a Challenge Pack, and a Treasure Map.
    policy_payload =

    encrypted_payload = pk_ursula.encrypt(policy_payload)

