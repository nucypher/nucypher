from nkms.crypto.encrypting_keypair import EncryptingKeypair


def test_encrypt_decrypt():
    data = b'xyz'
    alice = EncryptingKeypair()
    e = alice.encrypt(data)
    assert alice.decrypt(e) == data

    bob = EncryptingKeypair()
    e = bob.encrypt(data, pubkey=alice.pub_key)
    assert alice.decrypt(e) == data
