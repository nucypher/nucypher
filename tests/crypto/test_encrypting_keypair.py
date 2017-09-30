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
