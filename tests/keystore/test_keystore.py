import pytest

from datetime import datetime
from nucypher.keystore import keystore, keypairs


@pytest.mark.usefixtures(('nucypher_test_config', 'deploy_nucypher_contracts'))
def test_key_sqlite_keystore(test_keystore, bob):

    # Test add pubkey
    test_keystore.add_key(bob.stamp, is_signing=True)

    # Test get pubkey
    query_key = test_keystore.get_key(bob.stamp.fingerprint())
    assert bytes(bob.stamp) == bytes(query_key)

    # Test del pubkey
    test_keystore.del_key(bob.stamp.fingerprint())
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_key(bob.stamp.fingerprint())


def test_policy_arrangement_sqlite_keystore(test_keystore):
    alice_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)
    alice_keypair_enc = keypairs.EncryptingKeypair(generate_keys_if_needed=True)
    bob_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)

    hrac = b'test'

    # Test add PolicyArrangement
    new_arrangement = test_keystore.add_policy_arrangement(
            datetime.utcnow(), b'test', hrac, alice_pubkey_sig=alice_keypair_sig.pubkey,
            alice_signature=b'test'
    )

    # Test get PolicyArrangement
    query_arrangement = test_keystore.get_policy_arrangement(hrac)
    assert new_arrangement == query_arrangement

    # Test del PolicyArrangement
    test_keystore.del_policy_arrangement(hrac)
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_policy_arrangement(hrac)


def test_workorder_sqlite_keystore(test_keystore):
    bob_keypair_sig1 = keypairs.SigningKeypair(generate_keys_if_needed=True)
    bob_keypair_sig2 = keypairs.SigningKeypair(generate_keys_if_needed=True)

    hrac = b'test'

    # Test add workorder
    new_workorder1 = test_keystore.add_workorder(bob_keypair_sig1.pubkey, b'test0', hrac)
    new_workorder2 = test_keystore.add_workorder(bob_keypair_sig2.pubkey, b'test1', hrac)

    # Test get workorder
    query_workorders = test_keystore.get_workorders(hrac)
    assert {new_workorder1, new_workorder2}.issubset(query_workorders)

    # Test del workorder
    deleted = test_keystore.del_workorders(hrac)
    assert deleted > 0
    assert test_keystore.get_workorders(hrac).count() == 0
