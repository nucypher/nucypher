import datetime

from nkms.crypto.api import keccak_digest
from tests.utilities import MockNetworkyStuff


def test_grant(alice, bob, ursulas):
    networky_stuff = MockNetworkyStuff(ursulas)
    policy_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    n = 5
    uri = b"this_is_the_path_to_which_access_is_being_granted"
    policy = alice.grant(bob, uri, networky_stuff, m=3, n=n,
                expiration=policy_end_datetime)

    # The number of policies is equal to the number of Ursulas we're using (n)
    assert len(policy._accepted_contracts) == n

    # Let's look at the first Ursula.
    ursula = list(policy._accepted_contracts.values())[0].ursula

    # Get the kfrag, based in the hrac.
    proper_hrac = keccak_digest(bytes(alice.seal) + bytes(bob.seal) + uri)
    kfrag_that_was_set = ursula.keystore.get_kfrag(proper_hrac)
    assert kfrag_that_was_set
