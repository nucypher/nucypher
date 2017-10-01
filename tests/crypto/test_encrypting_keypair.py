import pytest
import random
from nkms.crypto.encrypting_keypair import EncryptingKeypair


def test_encrypt_decrypt():
    data = b'xyz'
    alice = EncryptingKeypair()
    e = alice.encrypt(data)
    assert alice.decrypt(e) == data

    bob = EncryptingKeypair()
    e = bob.encrypt(data, pubkey=alice.pub_key)
    assert alice.decrypt(e) == data


def test_reencrypt():
    data = b'Hello Bob'
    alice = EncryptingKeypair()
    bob = EncryptingKeypair()
    ursula = EncryptingKeypair()

    e = alice.encrypt(data)
    re_ab = alice.rekey(bob.pub_key)

    e_b = ursula.reencrypt(re_ab, e)

    assert bob.decrypt(e_b) == data


@pytest.mark.parametrize("num_shares,min_shares", [
    (10, 8),
    (3, 2),
    (5, 4),
    (100, 85),
    (100, 99),
    (1, 1),
    (3, 1)])
def test_reencrypt_m_n(num_shares, min_shares):
    data = b'Hello Bob'
    alice = EncryptingKeypair()
    bob = EncryptingKeypair()
    ursulas = [EncryptingKeypair() for i in min_shares]

    e = alice.encrypt(data)
    re_ab = alice.split_rekey(bob.pub_key, min_shares, num_shares)
    re_selected = random.sample(re_ab, min_shares)

    shares = [u.reencrypt(rk, e) for (u, rk) in zip(ursulas, re_selected)]

    e_b = bob.combine(shares)
    assert bob.decrypt(e_b) == data
