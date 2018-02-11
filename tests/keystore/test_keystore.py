import pytest

from datetime import datetime
from nkms.keystore import keystore, keypairs
from nkms.crypto import api as API
from umbral.keys import UmbralPrivateKey


def test_key_sqlite_keystore(test_keystore):
    keypair = keypairs.SigningKeypair(generate_keys_if_needed=True)

    # Test add pubkey
    new_key = test_keystore.add_key(keypair)

    # Test get pubkey
    query_key = test_keystore.get_key(keypair.fingerprint)
    assert new_key == query_key

    # Test del pubkey
    test_keystore.del_key(keypair.fingerprint)
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_key(keypair.fingerprint)

def test_policy_contract_sqlite_keystore(test_keystore):
    alice_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)
    alice_keypair_enc = keypairs.EncryptingKeypair(generate_keys_if_needed=True)
    bob_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)

    hrac = b'test'

    # Test add PolicyContract
    new_contract = test_keystore.add_policy_contract(
            datetime.utcnow(), b'test', hrac, alice_keypair_sig,
            alice_keypair_enc, bob_keypair_sig, b'test'
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
    bob_keypair_sig2 = keypairs.SigningKeypair(generate_keys_if_neeeded=True)

    hrac = b'test'

    # Test add workorder
    new_workorder1 = test_keystore.add_workorder(bob_keypair_sig1, b'test', hrac)
    new_workorder2 = test_keystore.add_workorder(bob_keypair_sig2, b'test', hrac)

    # Test get workorder
    query_workorders = test_keystore.get_workorders(hrac)
    assert set([new_workorder1, new_workorder2]).issubset(query_workorders)

    # Test del workorder
    test_keystore.del_workorders(hrac)
    with pytest.raises(keystore.NotFound):
        del_key = test_keystore.get_workorders(hrac)

def test_keyfrag_sqlite(self):
    kfrag_component_length = 32
    rand_sig = API.secure_random(65)
    rand_id = b'\x00' + API.secure_random(kfrag_component_length)
    rand_key = b'\x00' + API.secure_random(kfrag_component_length)
    rand_hrac = API.secure_random(32)

    kfrag = KFrag(rand_id+rand_key)
    self.ks.add_kfrag(rand_hrac, kfrag, sig=rand_sig)

    # Check that kfrag was added
    kfrag_from_datastore, signature = self.ks.get_kfrag(rand_hrac, get_sig=True)
    self.assertEqual(rand_sig, signature)

    # De/serialization happens here, by dint of the slicing interface, which casts the kfrag to bytes.
    # The +1 is to account for the metabyte.
    self.assertEqual(kfrag_from_datastore[:kfrag_component_length + 1], rand_id)
    self.assertEqual(kfrag_from_datastore[kfrag_component_length + 1:], rand_key)
    self.assertEqual(kfrag_from_datastore, kfrag)

    # Check that kfrag gets deleted
    self.ks.del_kfrag(rand_hrac)
    with self.assertRaises(keystore.KeyNotFound):
        key = self.ks.get_key(rand_hrac)
