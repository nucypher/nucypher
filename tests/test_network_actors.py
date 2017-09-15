from nkms.policy.models import PolicyGroup
from nkms.crypto.keys import KeyChain


def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():

    keychain_alice = KeyChain()
    keychain_bob = KeyChain()
    keychain_ursula = KeyChain()

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"
    kfrag_id = 74

    # Alice runs this to get a policy object.
    policy_group = PolicyGroup.dictate(keychain_alice.pubkey_sig,
                            keychain_bob.pubkey_sig,
                            resource_id,
                            kfrag_id
                            )

    for policy in PolicyGroup:
        policy.enact()


    ### policy.enact(self):
        ursula = find_ursula()
        payload = keychain_ursula.pubkey_enc("In real life, this will be a kFrag, a ChallengePack, and a TreasureMap")
        policy.offer(ursula, payload    )



