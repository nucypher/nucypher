import datetime

from nkms.characters import Ursula
from nkms.crypto.api import keccak_digest
from nkms.crypto.utils import BytestringSplitter
from nkms.keystore.keypairs import PublicKey
from tests.utilities import MockNetworkyStuff
from apistar.test import TestClient


def test_grant(alice, bob, ursulas):
    networky_stuff = MockNetworkyStuff(ursulas)
    policy_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    n = 5
    uri = b"this_is_the_path_to_which_access_is_being_granted"
    policy = alice.grant(bob, uri, networky_stuff, m=3, n=n, expiration=policy_end_datetime)

    # The number of policies is equal to the number of Ursulas we're using (n)
    assert len(policy._accepted_contracts) == n

    # Let's look at the first Ursula.
    ursula = list(policy._accepted_contracts.values())[0].ursula

    # Get the kfrag, based in the hrac.
    proper_hrac = keccak_digest(bytes(alice.seal) + bytes(bob.seal) + uri)
    kfrag_that_was_set = ursula.keystore.get_kfrag(proper_hrac)
    assert kfrag_that_was_set


def test_alice_can_get_ursulas_keys_via_rest(alice, ursulas):
    mock_client = TestClient(ursulas[0].rest_app)
    response = mock_client.get('http://localhost/public_keys')
    signing_key_bytes, encrypting_key_bytes = BytestringSplitter(PublicKey)(response.content, return_remainder=True)
    stranger_ursula_from_public_keys = Ursula.from_public_keys(signing=signing_key_bytes, encrypting=encrypting_key_bytes)
    assert stranger_ursula_from_public_keys == ursulas[0]
