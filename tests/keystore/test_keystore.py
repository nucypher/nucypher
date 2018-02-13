import pytest

from datetime import datetime
from nkms.keystore import keystore, keypairs
from nkms.crypto import api as API
from umbral.keys import UmbralPrivateKey


def test_key_sqlite_keystore(test_keystore):
    keypair = keypairs.SigningKeypair(generate_keys_if_needed=True)

    # Test add pubkey
    test_keystore.add_key(keypair)

    # Test get pubkey
    query_key = test_keystore.get_key(keypair.get_fingerprint())
    assert keypair.serialize_pubkey() == query_key.serialize_pubkey()

    # Test del pubkey
    test_keystore.del_key(keypair.get_fingerprint())
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_key(keypair.get_fingerprint())


def test_policy_contract_sqlite_keystore(test_keystore):
    alice_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)
    alice_keypair_enc = keypairs.EncryptingKeypair(generate_keys_if_needed=True)
    bob_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)

    hrac = b'test'

    # Test add PolicyContract
    new_contract = test_keystore.add_policy_contract(
            datetime.utcnow(), b'test', hrac, alice_pubkey_sig=alice_keypair_sig,
            alice_signature=b'test'
    )

    # Test get PolicyContract
    query_contract = test_keystore.get_policy_contract(hrac)
    assert new_contract == query_contract

    # Test del PolicyContract
    test_keystore.del_policy_contract(hrac)
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_policy_contract(hrac)


def test_workorder_sqlite_keystore(test_keystore):
    bob_keypair_sig1 = keypairs.SigningKeypair(generate_keys_if_needed=True)
    bob_keypair_sig2 = keypairs.SigningKeypair(generate_keys_if_needed=True)

    hrac = b'test'

    # Test add workorder
    new_workorder1 = test_keystore.add_workorder(bob_keypair_sig1, b'test0', hrac)
    new_workorder2 = test_keystore.add_workorder(bob_keypair_sig2, b'test1', hrac)

    # Test get workorder
    query_workorders = test_keystore.get_workorders(hrac)
    assert set([new_workorder1, new_workorder2]).issubset(query_workorders)

    # Test del workorder
    test_keystore.del_workorders(hrac)
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_workorders(hrac)
