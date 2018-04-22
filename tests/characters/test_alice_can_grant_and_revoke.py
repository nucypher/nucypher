import datetime

from apistar.test import TestClient

from nkms.characters import Ursula
from nkms.crypto.api import keccak_digest
from nkms.crypto.constants import PUBLIC_KEY_LENGTH
from nkms.crypto.powers import SigningPower, EncryptingPower
from bytestring_splitter import BytestringSplitter
from umbral.fragments import KFrag
from umbral.keys import UmbralPublicKey
import maya


def test_grant(alice, bob):
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    n = 5
    uri = b"this_is_the_path_to_which_access_is_being_granted"
    policy = alice.grant(bob, uri, m=3, n=n,
                          expiration=policy_end_datetime)

    # The number of policies is equal to the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) == n

    # Let's look at the first Ursula.
    ursula = list(policy._accepted_arrangements.values())[0].ursula

    # Get the Policy from Ursula's datastore, looking up by hrac.
    proper_hrac = keccak_digest(bytes(alice.stamp) + bytes(bob.stamp) + uri)
    retrieved_policy = ursula.datastore.get_policy_arrangement(proper_hrac.hex().encode())

    # TODO: Make this a legit KFrag, not bytes.
    retrieved_k_frag = KFrag.from_bytes(retrieved_policy.k_frag)

    # TODO: Implement KFrag.__eq__
    found = False
    for k_frag in policy.kfrags:
        if bytes(k_frag) == bytes(retrieved_k_frag):
            found = True
    assert found


def test_alice_can_get_ursulas_keys_via_rest(ursulas):
    mock_client = TestClient(ursulas[0].rest_app)
    response = mock_client.get('http://localhost/public_keys')
    splitter = BytestringSplitter(
        (UmbralPublicKey, PUBLIC_KEY_LENGTH),
        (UmbralPublicKey, PUBLIC_KEY_LENGTH)
    )
    signing_key, encrypting_key = splitter(response.content)
    stranger_ursula_from_public_keys = Ursula.from_public_keys({SigningPower: signing_key,
                                                               EncryptingPower: encrypting_key}
                                                            )
    assert stranger_ursula_from_public_keys == ursulas[0]
