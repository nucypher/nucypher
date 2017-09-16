from nkms.crypto.keys import KeyChain

from nkms.policy.models import PolicyGroup


def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():
    keychain_alice = KeyChain()
    keychain_bob = KeyChain()
    keychain_ursula = KeyChain()

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"
    kfrag_id = 74

    # Alice runs this to get a policy object.
    policy_group = PolicyGroup.craft(keychain_alice.pubkey_sig,
                                       keychain_bob.pubkey_sig,
                                       resource_id,
                                       kfrag_id
                                       )

    policy_group.transmit()
